---
count: 0
---

# Broken

Every declaration below is deliberately wrong — one per `scan.py --check`
finding class. Nothing else in this fixture vault may be broken.

metabind.parse-error: `INPUT[inlineSelect(option(a), option(b)]`

metabind.unknown-field-type: `INPUT[bogusType:count]`

metabind.unknown-argument: `INPUT[text(bogusArgument):count]`

metabind.argument-not-allowed: `INPUT[text(minValue(1)):count]`

metabind.argument-arity: `INPUT[inlineSelect(option()):count]`

metabind.argument-value: `INPUT[slider(minValue(abc)):count]`

metabind.duplicate-argument: `INPUT[text(title(one), title(two)):count]`

metabind.inline-not-allowed: `INPUT[select(option(a)):count]`

metabind.unresolved-button-id: `BUTTON[no-such-button]`

metabind.missing-property (--strict only): `INPUT[text:neverDeclared]`

metabind.unresolved-note (--strict only): `INPUT[text:No Such Note#title]`

metabind.button-config, missing the required `label` key, setting both
`action` and `actions`, and carrying an unknown key:

```meta-bind-button
style: primary
bogusKey: true
action:
  type: command
  command: editor:save-file
actions:
  - type: command
    command: editor:save-file
```

metabind.unknown-button-action:

```meta-bind-button
label: Bogus
style: default
action:
  type: notAnActionType
```

metabind.button-action-field, missing `ms` and carrying an unknown field:

```meta-bind-button
label: Nap
style: default
action:
  type: sleep
  bogusField: 1
```

metabind.button-config with an unknown style:

```meta-bind-button
label: Loud
style: neon
action:
  type: command
  command: editor:save-file
```

Malformed button YAML:

```meta-bind-button
label: Unbalanced
style: [default
```
