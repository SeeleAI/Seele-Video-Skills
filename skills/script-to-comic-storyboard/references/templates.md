# Templates

## Source trace

```markdown
# Source Trace

- Source type: screenplay | story description
- Target duration: 60–90 seconds

## Original input
Faithful copy or concise traceable summary of the user input.

## Locked facts
- Facts supplied by the user that must not change.

## Assumptions
- Explicitly mark every noncritical gap filled during adaptation, or `None`.

## Screenplay used for storyboarding
For screenplay input, include the supplied screenplay without changing facts. For a story description, include the concise drafted screenplay with simple scene headings, visible action, essential dialogue/audio, and a clear ending.

## Beat-to-shot mapping
- Opening beat → shots 01–04
- Development beat → shots 05–12
- Climax beat → shots 13–16
- Resolution beat → shots 17–18
```

Use the actual beat boundaries; the ranges above are illustrative. Every shot `01`–`18` must map to exactly one screenplay beat.

## Shot list JSON

```json
{
  "project": "Project name",
  "shots": [
    {
      "shot_id": "01",
      "duration_seconds": 4.0,
      "visible_action": "One observable action",
      "framing": "wide | medium | close-up",
      "camera": "locked | pan | track | tilt",
      "audio": "Dialogue, ambience, or silence",
      "continuity": {
        "character": "identity/pose anchor",
        "wardrobe": "garment and state",
        "props": "owner, state, location",
        "hands": "anatomical left/right",
        "screen_direction": "movement/gaze direction",
        "axis": "established side or explicit reset"
      },
      "visual_qa": {
        "mapping": "pass",
        "character": "pass",
        "wardrobe": "pass",
        "props": "pass",
        "hands": "pass",
        "axis": "pass",
        "notes": ""
      }
    }
  ]
}
```

Repeat through `18`. Allowed QA states: `pass`, `warn`, `fail`, `not_reviewed`.

## Story Bible

```yaml
characters:
  - id:
    identity_anchor:
    face_hair_build:
    wardrobe:
    distinguishing_marks:
    prohibited_changes:
locations:
  - id:
    fixed_geometry:
    entrances_exits:
    axis_anchor:
props:
  - id:
    owner:
    visual_anchor:
    initial_state:
    default_hand:
```

## Continuity ledger

```yaml
shots:
  - shot_id: "01"
    start_state:
    visible_change:
    end_state:
    character_positions:
    wardrobe_state:
    prop_state_and_hand:
    screen_direction:
    axis_state:
    next_shot_handoff:
```
