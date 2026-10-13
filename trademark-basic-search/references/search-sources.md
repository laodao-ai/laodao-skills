# Trademark Search Sources

Load this file when performing a basic trademark search and you need the official endpoints, known limitations, or wording boundaries.

## Official Entry Points

- USPTO search landing page: https://www.uspto.gov/trademarks/search
- USPTO TM Search app: https://tmsearch.uspto.gov/
- USPTO TM Search configuration: https://tmsearch.uspto.gov/configuration.json
- USPTO structured endpoint observed from the app config: https://tmsearch.uspto.gov/prod-v1-0-0/tmsearch
- WIPO Global Brand Database: https://www.wipo.int/en/web/global-brand-database
- WIPO Global Brand Database app: https://branddb.wipo.int/
- WIPO GBD FAQ: https://www.wipo.int/en/web/global-brand-database/faqs_branddb
- EUIPO availability guidance: https://www.euipo.europa.eu/en/trade-marks/before-applying/availability
- TMview: https://www.euipn.org/en/tools/TMview
- CNIPA query-account guidance observed in prior search: https://www.cnipa.gov.cn/jact/front/mailpubdetail.do?sysid=13&transactId=502906

## Known Limitations

- USPTO: the public web app is a SPA, but the app config exposes a structured backend endpoint. Always smoke-test the endpoint before trusting automated results.
- WIPO: the Global Brand Database web app may return ALTCHA verification. Do not bypass it. Record manual follow-up if automated access is blocked.
- WIPO data: the FAQ says the full database is not available for sale/download because of national-office agreements. Use the search UI or a professional search provider for formal review.
- EUIPO/TMview: the pages are front-end applications. Use the UI manually if automated parsing is unreliable.
- CNIPA: China trademark search can require a registered user/login. Record manual or agent/lawyer review for China.

## Default Software Classes

- Class 9: downloadable software, desktop apps, developer tools, embedded software.
- Class 42: SaaS, software development tools, cloud services, technical services.

Add adjacent classes for the product context, such as education/training, hardware, semiconductors, telecom, games, or ecommerce.

## Suggested Query Expansion

For a proposed mark `<brand>`:

- Exact: `<brand>`, uppercase, lowercase, spaced form, hyphenated form.
- Roots: stem words, abbreviations, phonetic variants.
- Suffix/prefix risks: `Kit`, `Lab`, `Works`, `Studio`, `Tools`, `Cloud`, `AI`.
- Industry neighbors: same audience, same buyer, same channel, same technical category.

## Reporting Boundary

Say:

- "No obvious exact match was found in the searched source."
- "This source could not be fully automated; manual review is needed."
- "This is a basic screening result, not formal clearance."

Do not say:

- "The trademark is available."
- "The mark is cleared."
- "There is no risk."
