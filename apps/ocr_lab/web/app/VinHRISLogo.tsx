type VinHRISLogoProps = {
  compact?: boolean;
  inverse?: boolean;
};

export function VinHRISLogo({ compact = false, inverse = false }: VinHRISLogoProps) {
  return (
    <span className={`vinhris-logo${compact ? " vinhris-logo-compact" : ""}${inverse ? " vinhris-logo-inverse" : ""}`}>
      <span className="vinhris-logo-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" role="img" focusable="false">
          <path d="M5 10.4 14.5 5.8 20 11.2 25.5 5.8 35 10.4 20 35 5 10.4Z" />
          <path d="m10.5 12.3 9.5 16 9.5-16-9.5 5.8-9.5-5.8Z" className="vinhris-logo-cut" />
          <circle cx="20" cy="10.5" r="2.4" className="vinhris-logo-sun" />
          <path d="M13.2 18.3h3.3M23.5 18.3h3.3M16.5 22.2h7" className="vinhris-logo-signal" />
        </svg>
      </span>
      {!compact ? <span className="vinhris-logo-wordmark">Vin<span>HRIS</span></span> : null}
    </span>
  );
}
