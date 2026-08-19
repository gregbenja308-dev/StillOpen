const SECRET_QUERY_KEYS = new Set([
  "token",
  "access_token",
  "refresh_token",
  "id_token",
  "api_key",
  "apikey",
  "key",
  "auth",
  "session",
  "sessionid",
  "sid",
  "password",
  "code",
  "email",
  "client_secret",
]);

export function redactUrl(url: string): string {
  try {
    const parsed = new URL(url);
    for (const name of [...parsed.searchParams.keys()]) {
      if (SECRET_QUERY_KEYS.has(name.toLowerCase())) {
        parsed.searchParams.set(name, "REDACTED");
      }
    }
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return url;
  }
}

export function isCloseableUrl(url: string): boolean {
  return (
    Boolean(url) &&
    !url.startsWith("chrome://") &&
    !url.startsWith("chrome-extension://") &&
    !url.startsWith("about:") &&
    !url.startsWith("edge://")
  );
}
