# INFENERGY - 10-Post Content Generation Forensic

## Experiment

- Runs: 10
- Images generated: 0
- External posts: 0
- Production state contaminated: NO
- Code/policies changed during sample: NO

## Outcome

- Text ready: 1
- Recovered and ready: 0
- Final failures: 9
- Success rate: 10.0%
- Runs with an initial check failure: 0

## Ten Runs

| # | Slot | Product / Topic | Candidates | Initial Problem | Recovery | Final Result | Score |
| --- | --- | --- | ---: | --- | --- | --- | ---: |
| 1 | morning | unknown | 0 | none | no | TEXT_READY | n/a |
| 2 | midday | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 3 | evening | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 4 | morning | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 5 | midday | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 6 | evening | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 7 | morning | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 8 | midday | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 9 | evening | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |
| 10 | morning | unknown | 0 | none | no | FAILED_DUPLICATE_FRESHNESS | n/a |

## Gate Scorecard

- **validation**: seen 10, initial failures 0, final blocks 0
- **quality**: seen 10, initial failures 0, final blocks 0
- **duplicate**: seen 10, initial failures 9, final blocks 9
- **presentation**: seen 10, initial failures 10, final blocks 0

## Run Stories

### TEST 01
The autonomous morning decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **TEXT_READY**.
Final decision reasons: none.

### TEST 02
The autonomous midday decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 03
The autonomous evening decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 04
The autonomous morning decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 05
The autonomous midday decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 06
The autonomous evening decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 07
The autonomous morning decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 08
The autonomous midday decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 09
The autonomous evening decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

### TEST 10
The autonomous morning decision selected `product-free` on `no recorded topic`.
It produced 0 generated candidate versions and finished as **FAILED_DUPLICATE_FRESHNESS**.
Final decision reasons: duplicate_exact_caption_within_window.

## Notes

The JSON companion contains full captured native payloads, attempt diagnostics, validation, duplicate, strategy, evidence, and presentation records. Image artifact gates are intentionally marked not tested.

