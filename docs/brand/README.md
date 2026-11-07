# PlantPilot brand

**From scan to service.** A factory silhouette and a navigation pointer: industrial space, and purposeful movement through it.

## Colours

| Name | Hex | Use |
| --- | --- | --- |
| Navy | `#182C3A` | The anchor colour, dark surfaces and text on pale ones |
| Mint | `#26D6BC` | The accent on dark surfaces |
| Teal | `#00A88F` | The accent on light surfaces, and the pressed accent in the viewer |
| Paper | `#F3F7F8` | Pale surfaces |

In the viewer they are the Tailwind colours `brand-navy`, `brand-mint`, `brand-teal` and `brand-paper`, defined in `app/web/tailwind.config.js`. Status colours are not brand colours: red, amber and green keep their meaning, so a brand colour never stands in for an equipment state.

## Logo rules

- Use `on-dark` on navy or other dark surfaces and `on-light` on pale ones.
- Keep clear space of at least a quarter of the icon's width around the mark.
- Preserve the proportions. Do not stretch, rotate or add shadows.
- At favicon sizes use the simplified favicon, not a scaled-down logo.

The lettering in the logos is outlined, so no font is needed to show them. The outlines come from DejaVu Sans, see [`FONT-NOTICE.txt`](FONT-NOTICE.txt). The viewer's text stays in Raleway.

## Files

| File | Use |
| --- | --- |
| `app/web/public/brand/` | What the page serves: favicons, app icons, web manifest, on-dark logos, link preview image |
| `plantpilot-horizontal-on-light.svg`, `plantpilot-horizontal-on-dark.svg` | The README header |
| `title-1920x1080-dark.png` | The video's opening title card |
| `background-1920x1080-dark.png` | The slide background |
| `logo-bug-600x192-dark.png` | The video's corner logo |

The repository holds only the assets the product, the README, the deck and the video use. The other logo variants and the social cards stay in the media kit outside git. The kit calls its headlines suggested brand copy, not performance claims, so the tagline is not a measured result.

For the GitHub repository's social preview, upload `app/web/public/brand/open-graph-1200x630-dark.png` in the repository settings.
