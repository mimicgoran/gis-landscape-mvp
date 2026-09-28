/**
 * Tekstualni helperi za frontend prikaz.
 *
 * `cyrillicToLatin` postoji zato što OSM podaci za Srbiju često koriste
 * ćirilicu za `name` tag (npr. "Дунав", "Панчево"), dok je ostatak UI-ja
 * (kategorije, dugmad, poruke) namjerno na latinici -- mješavina ćirilice i
 * latinice u istoj listi izgleda nedosljedno (korisnička odluka, vidi
 * docs/architecture-feasibility-review.md, sekcija 33). Srpska ćirilica i
 * latinica su u punoj, deterministièkoj 1:1 fonetskoj korespondenciji (za
 * razliku od npr. ruskog) -- transliteracija je zato jednostavno mapiranje
 * karakter-po-karakter, bez dvosmislenosti ili potrebe za NLP/rječnikom.
 */

const CYRILLIC_TO_LATIN_MAP = {
  А: "A", Б: "B", В: "V", Г: "G", Д: "D", Ђ: "Đ", Е: "E", Ж: "Ž", З: "Z",
  И: "I", Ј: "J", К: "K", Л: "L", Љ: "Lj", М: "M", Н: "N", Њ: "Nj", О: "O",
  П: "P", Р: "R", С: "S", Т: "T", Ћ: "Ć", У: "U", Ф: "F", Х: "H", Ц: "C",
  Ч: "Č", Џ: "Dž", Ш: "Š",
  а: "a", б: "b", в: "v", г: "g", д: "d", ђ: "đ", е: "e", ж: "ž", з: "z",
  и: "i", ј: "j", к: "k", л: "l", љ: "lj", м: "m", н: "n", њ: "nj", о: "o",
  п: "p", р: "r", с: "s", т: "t", ћ: "ć", у: "u", ф: "f", х: "h", ц: "c",
  ч: "č", џ: "dž", ш: "š",
};

/**
 * Transliteruje srpsku ćirilicu u latinicu. Karakteri koji nisu u mapi
 * (latinica, brojevi, razmaci, interpunkcija) prolaze nepromijenjeni --
 * sigurno je pozvati ovo na bilo kom tekstu, uključujući već-latinični.
 *
 * @param {string | null | undefined} text
 * @returns {string | null | undefined} isti tip kao ulaz (null/undefined prolaze kroz)
 */
export function cyrillicToLatin(text) {
  if (text == null) {
    return text;
  }
  let result = "";
  for (const char of text) {
    result += CYRILLIC_TO_LATIN_MAP[char] ?? char;
  }
  return result;
}
