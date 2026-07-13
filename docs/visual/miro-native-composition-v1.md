# Miro-native Composition Gate v1

Schauwerk treats Miro as a semantic visual medium rather than a generic card canvas. The gate supplements deterministic geometry with Miro-native composition rules.

## Required board contract

Every Visual System v2 board declares:

- `composition_profile: miro-native-composition.v1`;
- one `entry_frame` equal to the first reading-path frame;
- a finite `presentation_path` covering every frame exactly once;
- a dedicated `map` frame for overview and navigation.

## Shape grammar

Shapes encode information function before text is read:

| Semantic role | Default Miro shape |
| --- | --- |
| orientation | circle |
| entity or system | rectangle |
| evidence or store | can |
| decision | rhombus |
| risk | octagon |
| action | right arrow |

Boards containing at least three shapes must use at least two shape types. This blocks visually uniform card walls that can still satisfy spacing and density checks.

## Relation grammar

Connectors declare a semantic `relation_type`. Rendering maps that type to line shape, colour, stroke and endpoint:

- authority: dark straight line with filled arrow;
- flow: teal elbowed arrow;
- evidence: green dotted straight arrow;
- feedback: amber dashed curve;
- risk: red dashed warning arrow;
- association: neutral straight line without arrow.

Connector-rich boards must use at least two relation types. Captions remain useful, but they are no longer the only cue.

## Quality truth

The automatic score remains a contract score, not an aesthetic verdict. Human visual review stays separate. Remote Miro readback proves item and connector conformance, not pixel-identical rendering or universal visual quality.
