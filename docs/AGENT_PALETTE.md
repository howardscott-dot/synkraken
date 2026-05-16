# Agent Color Palette

Universal color assignments for agent identification across all Synkraken client interfaces.

## Principle

Agent colors are **fixed and universal**, not implementation-specific. Every Synkraken TUI, dashboard, or client should use the same assignments to ensure a consistent user experience.

## Assignments

| Agent | Dark (headers/names) | Light (chat text) | Hex Dark | Hex Light |
|-------|----------------------|-------------------|----------|-----------|
| `goose` | Grey | Silver | `#7F7F7F` | `#B0B0B0` |
| `hermes` | Amber | Gold | `#B38F00` | `#FFCC00` |
| `openclaw` | Coral | Salmon | `#CC4433` | `#E07060` |

## Rationale

- **Goose** (Grey/Silver) — Neutral, stands back, lets others be colorful
- **Hermes** (Amber/Gold) — Scholarly, warm, distinctive
- **OpenClaw** (Coral) — Energetic, complementary to synkraken green branding

## Usage

Use the dark shade for:
- Agent names in headers
- Message sender labels
- Status indicators

Use the light shade for:
- Chat message text
- Delivery body content
- Response bodies

## Extending the Palette

When adding new agents, follow these guidelines:

1. Choose colors that complement (not clash with) existing assignments
2. Ensure sufficient contrast against dark terminal backgrounds
3. Maintain distinct dark/light pairing for visual hierarchy
4. Document the new assignment in this file
5. Update the version number

## Example Implementations

### Terminal Colors (24-bit RGB)
```python
AGENT_COLORS = {
    'goose':     {'dark': (127, 127, 127), 'light': (176, 176, 176)},
    'hermes':    {'dark': (179, 143, 0),   'light': (255, 204, 0)},
    'openclaw':  {'dark': (204, 68, 51),   'light': (224, 112, 96)},
}
```

### ANSI Terminal (8-color fallback)
```python
AGENT_ANSI = {
    'goose':     {'dark': 8,  'light': 7},   # Grey / White
    'hermes':    {'dark': 3,  'light': 11},  # Yellow
    'openclaw':  {'dark': 1,  'light': 9},   # Red / Light Red
}
```

### CSS Variables
```css
:root {
    --goose-dark: #7F7F7F;
    --goose-light: #B0B0B0;
    --hermes-dark: #B38F00;
    --hermes-light: #FFCC00;
    --openclaw-dark: #CC4433;
    --openclaw-light: #E07060;
}
```

---

Version: 1.0.0