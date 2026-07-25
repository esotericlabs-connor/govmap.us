"use client";

/**
 * Root error boundary — only fires if the root layout itself throws, so it must
 * render its own <html>/<body> and can't rely on the app's CSS. Deliberately
 * minimal and inline-styled.
 */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          background: "#0b1220",
          color: "#f8fafc",
          textAlign: "center",
          padding: "1.5rem",
        }}
      >
        <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Something went wrong</h1>
        <p style={{ marginTop: "0.75rem", color: "#cbd5e1", maxWidth: "28rem" }}>
          The page failed to load. Please try again.
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            marginTop: "1.5rem",
            borderRadius: "9999px",
            border: "none",
            background: "#58A9E6",
            color: "#0b1220",
            padding: "0.625rem 1.5rem",
            fontSize: "0.875rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
