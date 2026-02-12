---
name: browser
description: Playwright browser automation — navigate, read, and interact with web pages using text snapshots and ref-based targeting.
metadata:
  xiaodazi:
    dependency_level: optional
    os: [darwin, linux]
    backend_type: tool
    tool_name: browser
    bins: []
    pip: ["playwright"]
---

# Browser Automation

Playwright-driven browser tool for web page interaction. Text-snapshot-first: reads pages as structured text, acts on elements by ref ID — no coordinate guessing, no screenshots needed.

## When to Use

- **browser tool**: Web pages in a browser (forms, dashboards, search results)
- **observe_screen + peekaboo**: Native desktop apps (Finder, Calendar, TextEdit, Numbers)

Do NOT use peekaboo for browser content. Do NOT use browser tool for native macOS apps.

## Core Workflow

```
1. navigate → open URL
2. snapshot → read page as text, get element refs [e1], [e2], ...
3. click/type/select → act on elements by ref
4. snapshot → verify result
```

Always snapshot before acting. Never guess refs — they change on each snapshot.

## Actions

### navigate — Open a URL

```
browser(action="navigate", url="https://example.com")
→ {title: "Example", url: "https://example.com"}
```

### snapshot — Read page content (PRIMARY)

```
browser(action="snapshot")
→ Page: Example Dashboard
  URL: https://example.com/dashboard
  
  Interactive elements (12):
    [e1] button: Submit
    [e2] textbox: Search...
    [e3] link: Documentation
    [e4] combobox: Select department
    [e5] checkbox: Remember me
```

Use this to understand the page. Returns text with ref IDs.

### click — Click an element by ref

```
browser(action="click", ref="e1")
→ {clicked: "e1"}
```

### type — Type text into a field

```
browser(action="type", ref="e2", text="quarterly report", clear=true)
→ {typed: "quarterly report", ref: "e2"}
```

- `clear=true`: Replace existing text (like Ctrl+A then type)
- `clear=false` (default): Append to existing text

### select — Choose dropdown option

```
browser(action="select", ref="e4", text="Engineering")
→ {selected: "Engineering", ref: "e4"}
```

### screenshot — Capture page image (RARE)

```
browser(action="screenshot")
→ {path: "/tmp/browser_xxx.png"}
```

Only use when snapshot text is insufficient (e.g., analyzing visual layout or images).

### tabs — Manage browser tabs

```
browser(action="tabs")
→ {tabs: [{id: "tab_1", title: "Dashboard", active: true}, ...]}

browser(action="tabs", tab_id="tab_2")
→ {active_tab: "tab_2", title: "Settings"}
```

### scroll — Scroll the page

```
# Scroll down 500 pixels
browser(action="scroll", scroll_y=500)

# Scroll up 300 pixels
browser(action="scroll", scroll_y=-300)

# Scroll within a specific element
browser(action="scroll", ref="e5", scroll_y=200)

# Horizontal scroll
browser(action="scroll", scroll_x=300, scroll_y=0)
```

### hover — Hover over an element

```
# Hover to trigger dropdown menu or tooltip
browser(action="hover", ref="e3")
→ {hovered: "e3"}
```

### drag — Drag element to another

```
# Drag source element to target element
browser(action="drag", source_ref="e2", target_ref="e7")
→ {dragged: "e2", to: "e7"}
```

### fill — Clear and fill text (reliable form filling)

```
# Clear existing text and fill new value (better than type for forms)
browser(action="fill", ref="e1", text="2026-02-09")
→ {filled: "e1", text: "2026-02-09"}
```

Use `fill` instead of `type` when you need to replace existing field content.

### close — Close browser

```
browser(action="close")
→ {message: "Browser closed"}
```

## Best Practices

1. **Snapshot first, act second** — Always run snapshot before click/type/select
2. **Text over screenshots** — Snapshot gives structured text (low tokens). Screenshot gives images (high tokens). Prefer snapshot.
3. **Verify after acting** — Run snapshot again after click/type to confirm the action succeeded
4. **Ref freshness** — Refs may change after navigation or page updates. Re-snapshot to get current refs.
5. **Form filling** — For multi-field forms: snapshot → type each field by ref → snapshot to verify → submit
6. **Dropdown matching** — If exact option text doesn't match, snapshot the dropdown to see available options

## Example: Fill a Web Form

```
# 1. Navigate to the form
browser(action="navigate", url="https://oa.example.com/expense")

# 2. Read the form
browser(action="snapshot")
# → [e1] textbox: Date, [e2] combobox: Category, [e3] textbox: Amount, ...

# 3. Fill fields
browser(action="type", ref="e1", text="2026-01-15", clear=true)
browser(action="select", ref="e2", text="Travel")
browser(action="type", ref="e3", text="356.00", clear=true)

# 4. Verify and submit
browser(action="snapshot")
# → Confirm all fields are filled correctly
browser(action="click", ref="e8")  # Submit button
```
