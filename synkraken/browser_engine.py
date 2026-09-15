from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import os
import socket
from threading import Lock
from urllib.parse import urlsplit


BROWSER_TOOLS = ['browser_open', 'browser_read', 'browser_click', 'browser_type', 'browser_scroll']


def origin_of(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Invalid browser URL')
    parsed = urlsplit(url)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTP or HTTPS URL without embedded credentials')
    return f'{parsed.scheme}://{parsed.netloc.lower()}'


def public_url(url: str, test_origins: list[str] = ()) -> bool:
    try:
        origin = origin_of(url)
        if origin in test_origins:
            return True
        parsed = urlsplit(url)
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (ValueError, OSError):
        return False


class BotBrowsers:
    def __init__(self, bots) -> None:
        self.bots = bots
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='synkraken-browser')
        self.playwright = None
        self.browser = None
        self.contexts = {}
        self.pages = {}
        self.refs = {}
        self.snapshots = {}
        self.blocked_origins = {}
        self.lock = Lock()
        self.test_origins = bots.fabric.config.get('engine', {}).get('browser_test_origins', [])

    def permitted_origins(self, bot_id: str) -> list[str]:
        return self.bots.storage.workspace_value('browser:' + bot_id).get('origins', [])

    def grant(self, bot_id: str, origin: str) -> None:
        origin = origin_of(origin)
        if not public_url(origin, self.test_origins):
            raise ValueError('Browser access to private or local services is disabled')
        origins = self.permitted_origins(bot_id)
        if origin not in origins:
            origins.append(origin)
        self.bots.storage.save_workspace_value('browser:' + bot_id, {'origins': origins})

    def view(self, bot_id: str) -> dict:
        with self.lock:
            return dict(self.snapshots.get(bot_id, {'open': False}))

    def act(self, bot_id: str, action: str, args: dict, budget=None, run_id: str = '') -> dict:
        self.bots.get(bot_id)
        if action not in {'open', 'read', 'click', 'type', 'point', 'scroll'}:
            raise ValueError('Unknown browser action')
        if action == 'open':
            url = args.get('url', '')
            origin = origin_of(url)
            if not public_url(url, self.test_origins):
                raise ValueError('Browser access to private or local services is disabled')
            if origin not in self.permitted_origins(bot_id):
                pending = next((card for card in self.bots.storage.chat_cards(bot_id)
                    if card['kind'] == 'browser_access' and card['status'] == 'pending'
                    and card['origin'] == origin and not card.get('probe')), None)
                if pending:
                    if run_id and pending.get('run_id') != run_id:
                        pending['run_id'] = run_id
                        self.bots.storage.save_chat_card(pending)
                    return {'status': 'waiting_for_user', 'card_id': pending['card_id']}
                return self.bots.workspace.card(bot_id, 'browser_access', origin=origin, url=url, run_id=run_id)
        return self.worker.submit(self._act, bot_id, action, args, budget).result(timeout=45)

    def _ensure(self, bot_id: str):
        if bot_id in self.pages and not self.pages[bot_id].is_closed():
            return self.pages[bot_id]
        if self.browser is None:
            try:
                from playwright.sync_api import sync_playwright
                self.playwright = sync_playwright().start()
                environment = {key: value for key, value in os.environ.items()
                    if key in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'DISPLAY', 'XDG_RUNTIME_DIR'}}
                self.browser = self.playwright.chromium.launch(headless=True, chromium_sandbox=True, env=environment)
            except Exception:
                raise ValueError('Browser runtime is unavailable. Install synkraken[browser] and run python -m playwright install chromium') from None
        if len(self.contexts) >= 4 and bot_id not in self.contexts:
            raise ValueError('Four bot browsers are already open; restart the daemon to release them')
        if bot_id in self.contexts:
            self.contexts[bot_id].close()
        reference = 'browser-session-' + bot_id
        vault = self.bots.providers.vault
        state = vault.get(reference) if vault.contains(reference) else None
        context = self.browser.new_context(viewport={'width': 1200, 'height': 800}, accept_downloads=False,
                                           service_workers='block', storage_state=state)
        context.set_default_timeout(10000)

        def route(request):
            url = request.request.url
            if public_url(url, self.test_origins) and origin_of(url) in self.permitted_origins(bot_id):
                request.continue_()
            else:
                if public_url(url, self.test_origins):
                    self.blocked_origins.setdefault(bot_id, set()).add(origin_of(url))
                request.abort('blockedbyclient')

        context.route('**/*', route)
        page = context.new_page()
        context.on('page', lambda popup: popup.close())
        page.on('dialog', lambda dialog: dialog.dismiss())
        self.contexts[bot_id] = context
        self.pages[bot_id] = page
        return page

    def _act(self, bot_id: str, action: str, args: dict, budget):
        if budget:
            budget.check()
        page = self._ensure(bot_id)
        try:
            if action == 'open':
                self.blocked_origins[bot_id] = set()
                page.goto(args['url'], wait_until='domcontentloaded', timeout=20000)
            elif action in {'click', 'type'}:
                target = self.refs.get(bot_id, {}).get(args.get('ref'))
                if target is None:
                    raise ValueError('Read the current page and use one of its element references')
                if action == 'click':
                    target.click(timeout=10000)
                else:
                    if target.get_attribute('type') == 'password':
                        raise ValueError('Password entry requires a secure browser handoff; never send passwords through chat')
                    text = args.get('text')
                    if not isinstance(text, str) or len(text) > 2000:
                        raise ValueError('Browser text must be at most 2000 characters')
                    if target.evaluate('(element) => element.tagName.toLowerCase()') == 'select':
                        try:
                            target.select_option(label=text)
                        except Exception:
                            target.select_option(value=text)
                    else:
                        target.fill(text)
            elif action == 'point':
                x, y = args.get('x'), args.get('y')
                if not all(isinstance(value, (float, int)) for value in (x, y)) or not (0 <= x <= 1200 and 0 <= y <= 800):
                    raise ValueError('Invalid browser coordinates')
                page.mouse.click(x, y)
            elif action == 'scroll':
                if args.get('direction') not in {'up', 'down'}:
                    raise ValueError('Scroll up or down')
                page.mouse.wheel(0, 600 if args['direction'] == 'down' else -600)
            return self._snapshot(bot_id, page)
        except ValueError:
            raise
        except Exception:
            raise ValueError('Browser action did not complete. Read the page again; it may have changed or requested a blocked origin') from None

    def _snapshot(self, bot_id: str, page) -> dict:
        elements, refs = [], {}
        for index, target in enumerate(page.locator('a:visible,button:visible,input:visible,textarea:visible,select:visible,[role="button"]:visible').element_handles()[:150]):
            if not target.is_visible():
                continue
            ref = str(index + 1)
            kind = target.get_attribute('type') or target.evaluate('(element) => element.tagName.toLowerCase()')
            label = target.get_attribute('aria-label') or target.get_attribute('placeholder') or target.inner_text()[:160]
            item = {'ref': ref, 'kind': kind, 'label': label}
            if kind == 'select':
                item['options'] = target.eval_on_selector_all('option', '(options) => options.map(o => ({label:o.label,value:o.value}))')
            elements.append(item)
            refs[ref] = target
        self.refs[bot_id] = refs
        snapshot = {'open': True, 'url': page.url, 'title': page.title(),
                    'text': page.locator('body').inner_text()[:12000], 'elements': elements,
                    'blocked_origins': sorted(self.blocked_origins.get(bot_id, set()))[:20],
                    'dependency_help': 'If required content is missing, use browser_open on the relevant blocked origin to request access, then reopen the original page. Do not request unrelated advertising or analytics sites.'}
        self.bots.providers.vault.put('browser-session-' + bot_id, self.contexts[bot_id].storage_state())
        image = page.screenshot(type='jpeg', quality=65, timeout=10000)
        with self.lock:
            self.snapshots[bot_id] = {**snapshot, 'image': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}
        return snapshot

    def close(self):
        if self.playwright:
            def cleanup():
                for bot_id, context in self.contexts.items():
                    self.bots.providers.vault.put('browser-session-' + bot_id, context.storage_state())
                if self.browser:
                    self.browser.close()
                self.playwright.stop()
            self.worker.submit(cleanup).result(timeout=15)
        self.worker.shutdown(wait=True)
