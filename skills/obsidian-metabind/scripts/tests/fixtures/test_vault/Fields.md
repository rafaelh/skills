---
count: 3
title: Fixture
nested:
  object: nested value
list:
  - one
  - two
---

# Fields

An inline input field: `INPUT[number:count]` and a view of it: `VIEW[{count}]`.

A fenced declaration:

```meta-bind
INPUT[toggle:done]
```

A declaration split over several lines:

```meta-bind
INPUT[select(
option(option a),
option(option b),
option(option c)
):choice]
```

A view field with a math expression and a write target:

```meta-bind
VIEW[{count} * 2][math:doubled]
```

A cross-note bind target: `INPUT[text:Other Note#title]`.

A nested bind target: `INPUT[text(showcase):nested["object"]]`.

A list index bind target: `INPUT[text:list[0]]`.

Escaped option strings: `INPUT[inlineSelect(option(0, 'don\'t do this'), option(1, 'do this \\')):choice]`.

A memory-scoped bind target, which never touches frontmatter:

```meta-bind
INPUT[text:memory^scratch]
```

And a global one: `INPUT[text:globalMemory^shared]`.

A templated input field takes its type from the template: `INPUT[someTemplate][]`.

## Fields in a callout

> [!note] Tracker
> Progress: `INPUT[slider(addLabels, minValue(0), maxValue(10)):count]`
> Done: `VIEW[{done}]`

## Fields in a table

| Property | Field                     | View            |
| -------- | ------------------------- | --------------- |
| count    | `INPUT[number:count]`     | `VIEW[{count}]` |
| done     | `INPUT[toggle:done]`      | `VIEW[{done}]`  |

## Embeds and JS

```meta-bind-embed
[[Other Note]]
```

```meta-bind-js-view
{count} as count
save to {doubled}
---
return engine.markdown.create(`count is ${context.bound.count}`);
```

```js-engine
const api = engine.getPlugin('obsidian-meta-bind-plugin').api;
return engine.markdown.create('hello');
```
