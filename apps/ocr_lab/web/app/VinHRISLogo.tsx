type VinHRISLogoProps = {
  compact?: boolean;
  inverse?: boolean;
};

export function VinHRISLogo({ compact = false, inverse = false }: VinHRISLogoProps) {
  return (
    <span className={`vinhris-logo${compact ? " vinhris-logo-compact" : ""}${inverse ? " vinhris-logo-inverse" : ""}`}>
      <span className="vinhris-logo-mark" aria-hidden="true">
        <b>V</b>
      </span>
      {!compact ? <span className="vinhris-logo-wordmark">Vin<span>HRIS</span></span> : null}
    </span>
  );
}
