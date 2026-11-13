// Builds the site search index (Pagefind) from _search_records.json, which scripts/build.py writes.
// Every newsletter issue, blog post and page goes in; newsletter issues link to Substack.
// Skips the work if nothing has changed since the last index.
import * as pagefind from "pagefind";
import fs from "node:fs";
import crypto from "node:crypto";

const records = JSON.parse(fs.readFileSync("_search_records.json", "utf8"));
const hash = crypto.createHash("sha256").update(JSON.stringify(records)).digest("hex");
const hashFile = "pagefind/records-hash.txt";
if (fs.existsSync(hashFile) && fs.readFileSync(hashFile, "utf8").trim() === hash) {
  console.log("Search index already up to date");
  process.exit(0);
}

const { index } = await pagefind.createIndex({ forceLanguage: "en" });
for (const r of records) {
  const meta = { title: r.title };
  if (r.date) meta.date = r.date;
  const { errors } = await index.addCustomRecord({
    url: r.url,
    content: r.content || r.title,
    language: "en",
    meta,
    filters: { type: [r.type] },
    sort: r.date ? { date: r.date } : {},
  });
  if (errors.length) console.log("Problem indexing", r.url, errors);
}
fs.rmSync("pagefind", { recursive: true, force: true });
const { errors } = await index.writeFiles({ outputPath: "pagefind" });
if (errors.length) { console.error(errors); process.exit(1); }
fs.writeFileSync(hashFile, hash + "\n");
console.log(`Search index built: ${records.length} records`);
await pagefind.close();
