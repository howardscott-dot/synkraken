from __future__ import annotations

NAME = "SYNKRAKEN"
TAGLINE = "tentacles in every runtime"

# ── kraken sigil ──────────────────────────────────────────────────────────
# 16 × 8 cell silhouette: domed head + four tentacles reaching down.
_KRAKEN_ROWS = (
    "    ████████    ",
    "  ████████████  ",
    " ██████████████ ",
    "████████████████",
    " ██  ██  ██  ██ ",
    " ██  ██  ██  ██ ",
    "█ █  █ █  █ █  █",
    "█ █  █ █  █ █  █",
)
KRAKEN_WIDTH  = max(len(r) for r in _KRAKEN_ROWS)   # 16
KRAKEN_HEIGHT = len(_KRAKEN_ROWS)                   # 8

# Vertical fade for the sigil — bright sunlit head → navy abyss tentacles.
_KRAKEN_FADE = (
    "\x1b[38;2;140;245;235m",  # row 1 — sunlit head crown
    "\x1b[38;2;110;230;230m",  # row 2
    "\x1b[38;2;80;200;215m",   # row 3
    "\x1b[38;2;50;170;200m",   # row 4 — full head
    "\x1b[38;2;35;140;185m",   # row 5 — upper tentacles
    "\x1b[38;2;25;110;165m",   # row 6
    "\x1b[38;2;15;80;140m",    # row 7 — lower tentacles
    "\x1b[38;2;10;50;110m",    # row 8 — tentacle tips, abyss
)
# 256-colour palette indices that approximate the same vertical fade for curses.
KRAKEN_ROW_XTERM256 = [123, 87, 81, 38, 31, 25, 19, 17]

# ── canonical wordmark — 6 rows, unchanged ────────────────────────────────
_WORDMARK_ROWS = (
    "███████╗██╗   ██╗███╗   ██╗██╗  ██╗██████╗  █████╗ ██╗  ██╗███████╗███╗   ██╗",
    "██╔════╝╚██╗ ██╔╝████╗  ██║██║ ██╔╝██╔══██╗██╔══██╗██║ ██╔╝██╔════╝████╗  ██║",
    "███████╗ ╚████╔╝ ██╔██╗ ██║█████╔╝ ██████╔╝███████║█████╔╝ █████╗  ██╔██╗ ██║",
    "╚════██║  ╚██╔╝  ██║╚██╗██║██╔═██╗ ██╔══██╗██╔══██║██╔═██╗ ██╔══╝  ██║╚██╗██║",
    "███████║   ██║   ██║ ╚████║██║  ██╗██║  ██║██║  ██║██║  ██╗███████╗██║ ╚████║",
    "╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝",
)
_WORDMARK_FADE = (
    "\x1b[38;2;140;245;235m",  # bright aqua / sunlit surface
    "\x1b[38;2;90;215;220m",   # light teal / shallow water
    "\x1b[38;2;50;170;200m",   # teal / mid water
    "\x1b[38;2;30;130;180m",   # ocean blue
    "\x1b[38;2;20;90;150m",    # deep blue
    "\x1b[38;2;10;50;110m",    # deep navy / abyss
)
_TAGLINE_COLOUR = "\x1b[38;2;40;150;190m"

WORDMARK_WIDTH = max(len(r) for r in _WORDMARK_ROWS)  # 77

# ── layout ────────────────────────────────────────────────────────────────
LEFT_INDENT       = 3
KRAKEN_GAP        = 3   # horizontal space between kraken and wordmark
KRAKEN_COL        = LEFT_INDENT                            # 3
WORDMARK_COL      = LEFT_INDENT + KRAKEN_WIDTH + KRAKEN_GAP  # 22
BANNER_WIDTH      = WORDMARK_COL + WORDMARK_WIDTH + LEFT_INDENT  # 102
BANNER_HEIGHT     = max(len(_KRAKEN_ROWS), len(_WORDMARK_ROWS) + 1)  # 8

# ── styles ────────────────────────────────────────────────────────────────
_RESET = "\x1b[0m"
_BOLD  = "\x1b[1m"
_DIM   = "\x1b[2m"

# ── glitch decoration ─────────────────────────────────────────────────────
_GLITCH_CHARS    = tuple(sorted('░▒▓█║═╔╗╚╝/\\|_-+#%@*:;.'))
_GLITCH_COLOURS  = ("\x1b[38;2;15;70;110m", "\x1b[38;2;8;40;80m")
_SCANLINE_COLOUR = "\x1b[38;2;8;30;70m"


def _lcg(seed: int) -> int:
    return (seed * 1664525 + 1013904223) & 0x7FFFFFFF


def _glitch_margin(seed: int, width: int, sparsity: int) -> str:
    rng = _lcg(seed)
    cells: list[str] = []
    for _ in range(width):
        rng = _lcg(rng)
        if rng % sparsity != 0:
            cells.append(' ')
            continue
        rng = _lcg(rng)
        c = _GLITCH_CHARS[rng % len(_GLITCH_CHARS)]
        rng = _lcg(rng)
        colour = _GLITCH_COLOURS[rng % len(_GLITCH_COLOURS)]
        cells.append(f"{colour}{_DIM}{c}{_RESET}")
    return ''.join(cells)


def _scanline_row(seed: int, width: int = BANNER_WIDTH) -> str:
    rng = _lcg(seed)
    cells: list[str] = []
    for _ in range(width):
        rng = _lcg(rng)
        if rng % 19 != 0:
            cells.append(' ')
            continue
        rng = _lcg(rng)
        c = _GLITCH_CHARS[rng % len(_GLITCH_CHARS)]
        cells.append(f"{_SCANLINE_COLOUR}{_DIM}{c}{_RESET}")
    return ''.join(cells).rstrip()


def _kraken_segment(row_idx: int) -> str:
    """Return one ANSI-coloured kraken row (or blank-padded if past height)."""
    if row_idx < KRAKEN_HEIGHT:
        return f"{_KRAKEN_FADE[row_idx]}{_KRAKEN_ROWS[row_idx]}{_RESET}"
    return ' ' * KRAKEN_WIDTH


def _wordmark_segment(row_idx: int) -> str:
    """Return one ANSI-coloured wordmark row, the tagline, or blank padding."""
    if row_idx < len(_WORDMARK_ROWS):
        colour = _WORDMARK_FADE[row_idx]
        prefix = _BOLD if row_idx == 0 else ''  # spec: slightly brighter top row
        return f"{prefix}{colour}{_WORDMARK_ROWS[row_idx]}{_RESET}"
    if row_idx == len(_WORDMARK_ROWS):
        return f"{_BOLD}{_TAGLINE_COLOUR}{TAGLINE}{_RESET}"
    return ''


def build_logo(scanlines: int = 1) -> list[str]:
    """Return the decorated logo as a list of ANSI-coloured strings.

    Each row is: <left margin> <kraken row> <gap> <wordmark row>.
    The kraken is 8 rows tall, the wordmark+tagline is 7 rows; the kraken's
    eighth tentacle row sits one line below the tagline, reaching down.
    """
    lines: list[str] = []

    for i in range(scanlines):
        lines.append(_scanline_row(seed=i * 7919 + 11))

    left = ' ' * LEFT_INDENT
    gap = ' ' * KRAKEN_GAP
    for i in range(BANNER_HEIGHT):
        kraken = _kraken_segment(i)
        wordmark = _wordmark_segment(i)
        lines.append(f"{left}{kraken}{gap}{wordmark}")

    for i in range(scanlines):
        lines.append(_scanline_row(seed=i * 7919 + 23))

    return lines


def print_logo(scanlines: int = 1) -> None:
    for line in build_logo(scanlines):
        print(line)


def get_logo_ansi(scanlines: int = 1) -> str:
    return '\n'.join(build_logo(scanlines))


# ── plain-text surface for curses & other non-ANSI renderers ─────────────
# Each row is the kraken + gap + wordmark, with NO escape sequences.
# Renderers can colour the kraken and wordmark independently using the
# offsets and fade-index arrays below.
LOGO_PLAIN_LINES = []
for _i in range(BANNER_HEIGHT):
    _kraken = _KRAKEN_ROWS[_i] if _i < KRAKEN_HEIGHT else ' ' * KRAKEN_WIDTH
    if _i < len(_WORDMARK_ROWS):
        _word = _WORDMARK_ROWS[_i]
    elif _i == len(_WORDMARK_ROWS):
        _word = TAGLINE
    else:
        _word = ''
    LOGO_PLAIN_LINES.append(' ' * LEFT_INDENT + _kraken + ' ' * KRAKEN_GAP + _word)

# Per-row colour-pair indices for renderers (length = BANNER_HEIGHT).
# -1 means "blank, no colouring needed".
LOGO_KRAKEN_FADE_INDEX = [i if i < KRAKEN_HEIGHT else -1 for i in range(BANNER_HEIGHT)]

# Wordmark fade indices: 0..5 for the six logo rows, 6 for the tagline,
# -1 for the trailing row (kraken's lone tentacle-tip row, no wordmark).
def _wordmark_index(i: int) -> int:
    if i < len(_WORDMARK_ROWS):
        return i
    if i == len(_WORDMARK_ROWS):
        return 6
    return -1

LOGO_WORDMARK_FADE_INDEX = [_wordmark_index(i) for i in range(BANNER_HEIGHT)]

# 256-colour palette indices for the wordmark vertical fade (same as before,
# plus a tagline shade at the end).
LOGO_ROW_XTERM256 = [123, 87, 38, 31, 25, 18, 32]
LOGO_ROW_FADE_INDEX = LOGO_WORDMARK_FADE_INDEX  # backward-compat alias


# ── legacy compatibility surface ──────────────────────────────────────────
LOGO_RAW = '\n' + '\n'.join(LOGO_PLAIN_LINES) + '\n'
LOGO_LINES = LOGO_PLAIN_LINES[:]
LOGO = LOGO_RAW.strip('\n') + '\n'
LOGO_COLORS = [(4, True), (4, True), (4, True), (3, False), (3, False), (2, False), (2, False), (2, False)]
