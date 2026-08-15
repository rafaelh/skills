---
count: 0
---

# Buttons

A button with a single action:

```meta-bind-button
label: Increment
style: primary
id: count-increment
hidden: true
action:
  type: updateMetadata
  bindTarget: count
  evaluate: true
  value: x + 1
```

A button with several actions:

```meta-bind-button
label: Reset and report
style: destructive
id: count-reset
hidden: true
actions:
  - type: updateMetadata
    bindTarget: count
    evaluate: false
    value: 0
  - type: sleep
    ms: 200
  - type: command
    command: editor:save-file
```

A button whose action runs JS, which rename.py must never rewrite:

```meta-bind-button
label: Report
style: default
id: count-report
hidden: true
action:
  type: inlineJS
  code: console.log(engine.getMetadata('count'));
```

A group reference to the buttons above:

`BUTTON[count-increment, count-reset]`

And one inside a fence:

```meta-bind
BUTTON[count-report]
```
