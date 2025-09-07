# External Assets

The following binary assets were removed from the repository. To obtain them, use the data URLs stored in the `assets/` directory.

- **Default Avatar**: see [`default-avatar.url`](assets/default-avatar.url) or the base64 data in [`default-avatar.base64`](assets/default-avatar.base64)
- **Inter Subset Font**: see [`inter-subset.woff2.url`](assets/inter-subset.woff2.url) or the base64 data in [`inter-subset.woff2.base64`](assets/inter-subset.woff2.base64)
- **DejaVu Sans Font**: see [`DejaVuSans.ttf.url`](assets/DejaVuSans.ttf.url) or the base64 data in [`DejaVuSans.ttf.base64`](assets/DejaVuSans.ttf.base64)
- **Menu Screenshot**: see [`menu_1.png.url`](assets/menu_1.png.url) or the base64 data in [`menu_1.png.base64`](assets/menu_1.png.base64)

You can download each asset by pasting the data URL into your browser's address bar or by decoding the corresponding base64 file, for example:

```sh
base64 -d assets/default-avatar.base64 > default-avatar.png
base64 -d assets/inter-subset.woff2.base64 > inter-subset.woff2
base64 -d assets/DejaVuSans.ttf.base64 > DejaVuSans.ttf
base64 -d assets/menu_1.png.base64 > menu_1.png
```
