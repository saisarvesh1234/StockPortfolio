
v11 changes
- Copied into its own folder with an updated responsive visual theme across all
  pages. Portfolio editing, price refresh, charts, transactions, imports and
  portfolio management remain interactive. v11 uses its own copy of the data.
- Run from this folder with: python app.py
- Opens at http://127.0.0.1:5001 (v10 can continue using port 5000).

v9 changes
- Multiple portfolios. The app now opens on a portfolio picker ("/") instead of the
  dashboard: create as many portfolios as you want, rename any of them in place
  (pencil icon), delete one (only when more than one exists), and click a card to
  open its dashboard. Every page and API call is scoped by a ?pf=<id> in the URL, so
  switching portfolios from the sidebar's "All portfolios" link and picking another
  is safe — each portfolio's stocks, transactions, prices and dividend data are
  stored separately (data/<id>.json) and can't leak into each other.
- Your existing single portfolio is migrated automatically on first run into a
  portfolio named "My Portfolio" — nothing is lost, no action needed.
- Fixed: dragging a JSON file onto the Download portfolio page could make the
  browser navigate away and open the file instead of importing it, if the drop
  landed a pixel outside the drop zone. The whole page now blocks that browser
  fallback, so a drop anywhere on the page is caught correctly.

v10 changes
- Redesigned "Your portfolios" as a full-screen page instead of a small centered
  box: a large hero with a scrolling ticker tape of your portfolios and their
  holding counts, a ledger-style "new portfolio" entry row, and portfolio cards
  with a ticker-style initials badge. Uses Fraunces (serif) for headings and IBM
  Plex Mono for everything else, with a navy/brass palette (auto-switches to a
  paler variant in light mode, same as the rest of the app). Verified in a headless
  browser at desktop, mobile widths, and both color schemes.
