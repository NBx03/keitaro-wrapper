/**
 * Strip duplicated leading "<id> " prefix from Keitaro offer names when rendering alongside "#<id>".
 */
export function formatOfferTitle(keitaroId: number, name: string): string {
  const prefix = `${keitaroId} `;
  return name.startsWith(prefix) ? name.slice(prefix.length).trimStart() : name;
}
