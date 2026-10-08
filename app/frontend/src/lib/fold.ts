/** Turkish-aware folding for matching: "İŞLEM", "işlem" and "islem" become the same text. */
export function fold(text: string | null | undefined): string {
  return String(text ?? '')
    .toLocaleLowerCase('tr-TR')
    .replace(/ı/g, 'i')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}
