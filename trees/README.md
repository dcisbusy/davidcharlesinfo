# Tree map: editing the species notes

The edible, medicinal and poisonous notes on the tree map come from **`species-uses.csv`**, a spreadsheet with one row per species or group of species.

To edit it, either:

- click the file on GitHub, then the pencil icon, and edit the text directly; or
- download it, open it in Excel, Numbers or Google Sheets, make your changes, save it as CSV (UTF-8), and upload it back to this folder.

The map picks up changes as soon as the site rebuilds. No other file needs to change.

## Columns

| Column | What it does |
|---|---|
| `name` | The heading for the row (only used in this spreadsheet). |
| `match` | Which trees the row applies to: words to look for in the councils' species name or its Latin name, separated by `\|` (meaning "or"). `\b` means a word boundary and `^` means "starts with", so `^pinus\b` matches "Pinus nigra" but not "Carpinus". **Rows are checked from top to bottom and the first match wins**, so put specific rows (Cherry laurel) above general ones (Cherry). |
| `latin` | The main Latin name, for reference. |
| `edible`, `medicinal`, `poisonous` | The note shown in each section of the popup. Leave a cell empty if it doesn't apply: a tree only appears in a layer if its cell is filled in. A row with all three empty stops those trees matching any later row. |
| `edible_sources`, `medicinal_sources`, `poisonous_sources` | The pages backing up that note, separated by spaces. Every note has at least two. They show as links under the note in the popup. |
| `risk` | For poisonous trees: `high` (can kill or seriously harm), `moderate` (likely to make someone ill) or `low` (mild, or a risk mainly to animals). |
| `research_notes` | The researchers' notes for you: claims dropped for lack of a second source, where sources disagreed, and rows that could be split. Not shown on the map. |

### How the notes were researched (November 2026)

Each row was researched separately, and every claim needed two reputable sources that were actually opened and read: NHS and poisons services, NCCIH/NIH, European Medicines Agency herbal monographs, peer-reviewed papers, Kew, the RHS, the Woodland Trust, university extension services (NC State, Cornell and others), ASPCA and the British Horse Society for animals, and the US Forest Service. Plants For A Future counted as one source at most. Claims with only one source were dropped. A separate check then went over the most safety-critical rows again.

`species-list.txt` lists every species name in the map area with its Latin name and number of trees, so you can see what the `match` column needs to catch. It is rebuilt with the tree data.
