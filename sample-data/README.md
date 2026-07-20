# Sample Data

Fictional statements for development and testing. No real accounts, no real people.

| File | Shape it exercises |
|---|---|
| `chase-checking-jan2026.csv` | Single signed `Amount` column, `MM/DD/YYYY` dates, separate transaction/post dates |
| `amex-card-jan2026.csv` | Split `Debit`/`Credit` columns, ISO dates, running balance column |

Between them these cover the two dominant CSV shapes and both common date formats.
`ZZQQ VENDOR 44821` in the checking file matches no starter rule on purpose — it's there
so the "needs review" path is always exercised.

Try it:

```bash
# with the backend running
curl -F "file=@sample-data/chase-checking-jan2026.csv" \
     "http://localhost:8000/api/imports?account_id=1"
```
