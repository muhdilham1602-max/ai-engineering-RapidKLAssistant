# Rapid KL lookup evaluation

Record the commit and the source ZIP hash from the bus manifest before each evaluation. Use the archived bus ZIP in `data/raw/` to build expected answers independently of the prepared lookup table.

| Case | Procedure | Passing result |
|---|---|---|
| Known stop | Search STESEN BRT SETIA JAYA and confirm stop ID 1005840. Join its stop times to trips and routes in the raw feed. | The displayed route IDs match the full reference set, including B1000. |
| Ambiguous name | Search TAMAN MUHIBBAH and compare the selectable IDs with matching records used by trips. | The rider can distinguish the IDs and must choose before seeing routes. |
| Unknown stop | Enter a name absent from the source. | The app reports no match in the snapshot. |
| Stop order | Select a trip with at least 11 stops. Sort its source stop times by integer stop_sequence. | All IDs match in order, including positions 2, 10 and 11. |
| Service coverage | Inspect the source and schedule labels on both views. | Both show the snapshot date and the limitation on live service information. |

For the Week 2 correctness target, select 50 supported lookups across routes, service days and directions. Save the input, expected IDs, displayed IDs and pass/fail for each case. Count an exact match only when the full set (or ordered sequence) agrees. Compare the percentage with the 90% target in [Week 2 evaluation criteria](../docs/week2_evaluation_criteria.md). Record failures by stop or trip ID so they can be reproduced. Natural-language intent and bilingual response checks apply when that interface is implemented.
