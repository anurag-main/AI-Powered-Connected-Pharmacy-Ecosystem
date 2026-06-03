import "@/globals.css";
import { Geist, Geist_Mono } from "next/font/google";
import Head from "next/head";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

const geistMono = Geist_Mono({
    variable: "--font-geist-mono",
    subsets: ["latin"],
});

export default function App({ Component, pageProps }) {
    // Per-page layouts: a page may define Page.getLayout to wrap itself.
    const getLayout = Component.getLayout || ((page) => page);

    return (
        <>
            <Head>
                <title>PharmaBill — Voice Billing</title>
                <meta name="description" content="Speak a medicine order; the bill fills itself." />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                {/* Material Symbols font + ms-loaded gate live in pages/_document.jsx
                    (Next requires external stylesheets/scripts there, not in _app Head). */}
            </Head>
            <style jsx global>{`
                :root {
                    --font-geist-sans: ${geistSans.style.fontFamily};
                    --font-geist-mono: ${geistMono.style.fontFamily};
                }
            `}</style>
            <main className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}>
                {getLayout(<Component {...pageProps} />)}
            </main>
        </>
    );
}
