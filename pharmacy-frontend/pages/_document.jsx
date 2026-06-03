import { Html, Head, Main, NextScript } from "next/document";

/**
 * Custom Document — the right place (per Next.js) for external stylesheets and
 * head scripts. Loads Google Material Symbols Outlined and the `ms-loaded` gate
 * script that prevents icon ligature names flashing as text on cold cache.
 */
export default function Document() {
    return (
        <Html lang="en">
            <Head>
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link
                    rel="stylesheet"
                    href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,300..700,0..1,-50..200&display=block"
                />
                <script
                    dangerouslySetInnerHTML={{
                        __html: `(function(){var d=document,h=d.documentElement,f='1em "Material Symbols Outlined"',s=Date.now();function done(){h.classList.add('ms-loaded')}if(!d.fonts||!d.fonts.load){setTimeout(done,800);return}function attempt(){if(Date.now()-s>15000){done();return}d.fonts.load(f).then(function(fs){if(fs&&fs.length>0){done()}else{setTimeout(attempt,100)}}).catch(function(){done()})}attempt()})();`,
                    }}
                />
            </Head>
            <body>
                <Main />
                <NextScript />
            </body>
        </Html>
    );
}
