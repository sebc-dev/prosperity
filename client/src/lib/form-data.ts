// Lit un champ texte d'un `FormData` en `string`. `FormData.get` renvoie `string | File | null`
// (un File pour un `<input type="file">`) ; nos formulaires n'ont que des champs texte, mais ce
// garde-fou évite la stringification `[object Object]` d'un File (et satisfait `no-base-to-string`).
export function fieldValue(form: FormData, name: string): string {
  const v = form.get(name)
  return typeof v === 'string' ? v : ''
}
