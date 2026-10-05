# PDF and remote human-test decision

Date: 2026-10-05, Europe/Berlin. Owner: prototype integration.

User authorized more geometric/organic test forms and PDF export so a crocheter
away from this computer can use the instructions. The existing layout is
adequate. This authorizes the local feature, not publication or remote hosting.

## Primary-source comparison

Yarnify3D's [editor documentation](https://yarnify3d.com/docs/editor/editor-overview),
rechecked on this date, describes printable PDF export with optional end,
section and row pictures. It also documents synchronized selection, stitch
counts and preview updates. These are vendor descriptions, not independently
tested physical results. Their live-crochet page was unavailable to the web
reader in this follow-up; the dated earlier research is retained without
claiming a newly observed change.

ENGINEERING DECISION: implement our own printable instructions from the exact
validated construction, material values and artifact identity. Include a
report worksheet so a remote tester can return measurements and problem
rounds without installing this app. Keep PDF source identity visible after
printing, and distinguish compound instruction count from produced stitches.
No competitor source code, patterns, images, fonts or assets are reused.

## Adopted and later improvements

- Implemented scope: six bounded shape choices, example dimensions that preserve
  the crocheter's gauge, PDF instructions and printable test feedback.
- User test: compare sphere, capsule and pear with the same measured material;
  record actual widths/heights, stuffing state and required pattern changes.
- FUTURE: show a clearly separated desired silhouette beside construction and,
  when calibrated, predicted fabric. A target illustration must never feed the
  independent forward model or substitute for physical evidence.
- FUTURE: attach notes to specific instructions/rounds and compare measurements
  across revisions before proposing reviewed calibration updates.
- FUTURE: separate component assembly, joining and color-work contracts for
  figures; schema expressiveness alone does not establish supported generation.
- FUTURE: the separate mobile app remains requested, after this browser test.

These are our product choices. No claim that our full product or physical
accuracy is superior has been established by this comparison.

## Dependency and license review

ReportLab is justified by reliable A4 pagination and text export; no second
browser, cloud PDF service or custom PDF parser/writer is needed. Vendor
[paragraph documentation](https://docs.reportlab.com/reportlab/userguide/ch6_paragraphs/)
and [font documentation](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/)
were checked. Runtime declaration: reportlab >=4.4.9,<5; tested 4.4.9 from
[official PyPI](https://pypi.org/project/reportlab/4.4.9/). Its exact wheel's
dist-info/licenses/LICENSE permits source/binary redistribution under BSD
notice and non-endorsement conditions. Retain dependency notices on distribution.
Helvetica is a standard PDF font; no third-party font file is vendored or
embedded. Unsupported input characters are rejected rather than replaced by
missing glyphs. External markup in yarn text is escaped.

Transitive runtime wheels inspected: Pillow 12.3.0 declares MIT-CMU;
charset-normalizer 3.5.2 declares MIT. Test-only dependencies inspected:
types-reportlab 4.4.9.20260215 declares Apache-2.0 and pypdf 6.13.3 declares
BSD-3-Clause. These permissive licenses are compatible with retaining notices.
Wheel hashes were checked against official PyPI metadata before installation.
Dependencies remain packages rather than copied implementation snippets.
PDF generation uses local text/vector output and no remote service, image
retrieval or telemetry integration. This is a scoped dependency review, not a
complete security audit of every optional library feature.

Semantic validation and export round trip remain construction prerequisites.
PDF readability is an additional presentation check; it is not a new independent
semantic or physical gate. All test patterns remain NOT_VERIFIED and UNTESTED.
