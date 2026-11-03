import "../index.css";
import "../styles/theme.css";
import "../styles/backend-ready.css";
import "../styles/workforce-ui.css";

import Providers from "./providers.jsx";

export const metadata = {
    title: "Joross Farm",
    description:
        "JoRoss Farm Analytics and Production Monitoring System",
    manifest: "/manifest.webmanifest",
    applicationName: "JoRoss Farm",
    appleWebApp: { capable: true, title: "JoRoss Farm", statusBarStyle: "default" },
    icons: {
        icon: [{ url: "/favicon-farm.png?v=1", type: "image/png", sizes: "32x32" }],
        apple: "/images/Jorros%20Logo%201.png",
    },
};

export const viewport = {
    width: "device-width",
    initialScale: 1,
    themeColor: "#006400",
};

export default function RootLayout({ children }) {
    return (
        <html
            lang="en"
            suppressHydrationWarning
            data-scroll-behavior="smooth"
        >
            <head>
                <link href="/fonts/local-fonts.css" rel="stylesheet" />
                <link href="/fonts/fontawesome.min.css" rel="stylesheet" />
            </head>

            <body suppressHydrationWarning>
                <Providers>
                    {children}
                </Providers>
            </body>
        </html>
    );
}
