interface Props {
  color: string | undefined;
}

export function Swatch({ color }: Props) {
  return <span className="swatch" aria-hidden="true" style={{ background: color ?? "var(--neutral)" }} />;
}
