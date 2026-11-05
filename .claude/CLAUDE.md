# milcahjoseph.com

This repo is Milcah Joseph's portfolio site. GitHub Pages publishes the `main` branch to https://milcahjoseph.com (custom domain in `CNAME`) within minutes of any change. Pages are plain HTML, CSS and JavaScript, with D3 for charts. Pages runs its default Jekyll build: folders starting with a dot or underscore are not published, and any other Markdown file becomes a public page.

## How to make changes

- Never push to `main` and never merge a pull request. Milcah reviews and merges every change herself.
- Commit as Milcah: before your first commit, run `git config user.name "Milcah M. Joseph"` and `git config user.email "98636311+M1ck3yJ0@users.noreply.github.com"`. Add no Co-Authored-By line, session link or other Claude attribution to commits or pull requests.
- Do each piece of work on a new branch from the latest `main` and push the branch. Don't open or edit pull requests. Milcah opens them herself.
- Commit after every step, so each commit holds one small change: creating a folder, adding a file, making a separate edit. Git can't store an empty folder, so a new folder gets a `.gitkeep` file in its own commit. Give each commit a plain message saying what changed and why.
- After pushing, give Milcah the link to open the pull request, `https://github.com/M1ck3yJ0/M1ck3yJ0.github.io/pull/new/<branch>`, and say in plain words what changed and what to check before merging.
- Don't edit `CNAME` or delete files unless she asks.

## Where things live

- `index.html`: the home page, including the portfolio grid of project cards.
- `projects/<project>/`: one folder per project page.
- `assets/`: images. Each card uses `<name>_thumb.png` and a hover GIF, `<name>_hover.gif`. Link preview images are `<name>_meta_thumb.png`, 1200 x 630.

## Before committing a page

- Render it at phone (390 px) and desktop (1280 px) widths with `_tools/check_page.py` (usage at the top of the file) and look at the screenshot sheets it saves: charts drawn, text readable, nothing cut off or overflowing.
- Give it a title, a meta description and an `og:image` set to the full URL of an image file in `assets/`, so LinkedIn shows a preview picture.
- Check that every link works.
- Use American spelling and no em or en dashes in page text.
- Give a new project a card in the `index.html` portfolio grid, matching the existing cards.
