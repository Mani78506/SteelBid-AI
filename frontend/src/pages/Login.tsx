import * as React from "react";
import { useNavigate } from "react-router";
import { useAuth } from "@/lib/auth";
import LoginBackground from "./login/LoginBackground";
import LoginBranding from "./login/LoginBranding";
import LoginForm from "./login/LoginForm";

export default function Login() {
  const { login, me } = useAuth();
  const navigate = useNavigate();

  React.useEffect(() => { if (me) navigate("/", { replace: true }); }, [me, navigate]);

  const submit = async (email: string, password: string) => {
    await login(email, password);
    navigate("/", { replace: true });
  };

  return (
    <div className="relative min-h-screen w-full">
      <LoginBackground />

      {/* Mobile-only overlay: strengthen dim so the card reads cleanly */}
      <div className="absolute inset-0 bg-[#060d1c]/55 lg:hidden" aria-hidden="true" />

      <div className="relative z-10 grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
        {/* Left: brand story (desktop) */}
        <LoginBranding />

        {/* Right: login card — on desktop it floats at viewport center like the reference */}
        <div className="flex items-center justify-center px-4 py-10 sm:px-8
          lg:absolute lg:inset-0 lg:z-20 lg:justify-center lg:pl-[2%]">
          {/* Compact brand header for mobile/tablet */}
          <div className="absolute top-5 left-5 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2f6fde]">
              <span className="text-sm font-bold text-white">SB</span>
            </div>
            <div>
              <p className="text-sm font-bold leading-tight text-white">SteelBid AI</p>
              <p className="text-[10px] text-slate-400">Steel Business Operating System</p>
            </div>
          </div>
          <LoginForm onSubmit={submit} />
        </div>
      </div>
    </div>
  );
}
