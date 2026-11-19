interface Props {
  cities: readonly string[];
  city: string | null;
  onChoose: (city: string | null) => void;
}

export function CityToggle({ cities, city, onChoose }: Props) {
  if (cities.length < 2) return null;
  const options: (string | null)[] = [null, ...cities];
  return (
    <div className="cities" role="radiogroup" aria-label="City" data-testid="cities">
      {options.map((option) => (
        <button
          key={option ?? ""}
          type="button"
          role="radio"
          aria-checked={option === city}
          className={option === city ? "city is-on" : "city"}
          onClick={() => onChoose(option)}
        >
          {option ?? "All"}
        </button>
      ))}
    </div>
  );
}
