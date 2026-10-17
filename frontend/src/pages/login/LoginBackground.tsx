export default function LoginBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-[#0a1628]" aria-hidden="true">
      {/* Clean industrial scene asset — no baked-in UI elements */}
      <img
        src="/assets/login-industrial.svg"
        alt=""
        className="absolute inset-0 h-full w-full object-cover"
        draggable={false}
      />
      {/* Left navy readability gradient (mirrors the reference) */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#060d1c]/95 via-[#0a1628]/70 to-transparent lg:w-[62%]" />
      {/* Bottom vignette for feature text */}
      <div className="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-[#060d1c]/80 to-transparent" />
      {/* Subtle top vignette */}
      <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[#060d1c]/50 to-transparent" />
    </div>
  );
}
