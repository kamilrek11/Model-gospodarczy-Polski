export const SYNTHETIC_TEXT = "DANE SYNTETYCZNE – nie są to dane GUS/MF";

/** Stały, niezamykalny baner: dane w bazie są wymyślone (scripts/seed_fixtures.py), nie prawdziwe. */
export function SyntheticBanner({ synthetic }: { synthetic: boolean }) {
  if (!synthetic) return null;
  return (
    <div className="synthetic-banner" role="status">
      <strong>{SYNTHETIC_TEXT}</strong>
      <span> Wykresy i liczby służą wyłącznie demonstracji działania symulatora.</span>
    </div>
  );
}
