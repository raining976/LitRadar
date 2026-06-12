# LitRadar Topic/Search/Radar Refinement Design

## Goal

Refine the MVP around three core workflows: research-direction setup, paper search ranking, and Today Radar recommendation refresh.

## Design

Research directions become user-facing categories with only three visible configuration concepts: display name, fuzzy-match keywords, and CV/AI-focused CCF-A/B venues. The existing backend `ResearchTopic` model can keep legacy fields for compatibility, but the UI will remove description and Obsidian folder from direction setup. The current direction remains a highlighted card. The add card should have the same footprint as normal topic cards, use a rounded dashed style, and open a modal form instead of showing the form inline. Editing an existing direction opens the same modal.

Paper search keeps arXiv as the candidate source, then applies local scoring to title and abstract. The scoring input includes the search query, selected topic keywords, and selected venue names. Results are sorted by score. Results expose matched keywords/venues so the frontend can highlight those terms inside titles/abstract snippets and show result count above the input on the left when results exist.

Today Radar uses the current research direction only. On each manual refresh, it should fetch candidates, score them, select random papers with score greater than 60 up to the configured limit, and replace today's displayed recommendation set without treating prior recommendations as a cache that blocks showing a different set. The recommendation-count control should display as a left/right row with label and value; editing happens through a button that opens a small editing state and save action rather than a permanently visible number input.

## CCF Venue Scope

For this MVP, provide built-in CV/AI-oriented CCF-A/B options first. Use labels such as `CCF-A · CVPR`, `CCF-A · ICCV`, `CCF-A · NeurIPS`, `CCF-A · ICML`, `CCF-A · AAAI`, `CCF-A · IJCAI`, `CCF-A · TPAMI`, `CCF-B · ECCV`, `CCF-B · ICLR`, `CCF-B · ACM MM`, `CCF-B · TNNLS`, and `CCF-B · Pattern Recognition`. Store the selected venue names in the existing `arxiv_categories` payload field for now, but rename it in TypeScript/UI only as venue preferences.

## Error Handling

If arXiv is unavailable, keep the existing 503 JSON error. If no scored candidate exceeds 60 for Today Radar, return an empty recommendation list and let the UI explain that the current direction did not produce high-confidence candidates.

## Testing

Backend tests should cover scoring, matched-term extraction, search ranking payload shape, and Today Radar replacement/random candidate behavior above score 60. Frontend API tests should cover unchanged payload compatibility if the field remains `arxiv_categories`. Frontend build should verify the modal/topic/search/radar UI compiles.
