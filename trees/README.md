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
| `match` | Which trees the row applies to: words to look for in the councils' species name or its Latin name, separated by `\|` (meaning "or"). `\b` means a word boundary, so `\byew\b` matches "Yew" but not "Yewberry". **Rows are checked from top to bottom and the first match wins**, so put specific rows (Cherry laurel) above general ones (Cherry). |
| `latin` | The main Latin name, for reference. |
| `edible`, `medicinal`, `poisonous` | The note shown in each section of the popup. Leave a cell empty if it doesn't apply: a tree only appears in a layer if its cell is filled in. A row with all three empty stops those trees matching any later row. |
| `risk` | For poisonous trees: `high` (can kill or seriously harm), `moderate` (likely to make someone ill) or `low` (mild, or a risk mainly to animals). |
| `sources` | Links backing up the notes, separated by spaces. |
| `checked` | `yes` if the notes were checked against the specific sources listed; `no` if only the general Plants For A Future (pfaf.org) page is listed and the notes still need checking. |

`species-list.txt` lists every species name in the map area with its Latin name and number of trees, so you can see what the `match` column needs to catch. It is rebuilt with the tree data.
