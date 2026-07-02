export function backendCallPathRe(name: string): RegExp {
  return new RegExp(`(^|[^A-Za-z0-9_./-])/${name}(?:/[a-z0-9][a-z0-9_-]*)?\\s*\\(`);
}
