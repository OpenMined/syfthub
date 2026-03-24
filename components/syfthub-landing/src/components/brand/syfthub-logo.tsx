import Image from "next/image";

interface SyftHubLogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  dark?: boolean;
}

const sizes = {
  sm: { icon: 24, text: "text-[14px]" },
  md: { icon: 28, text: "text-[15px]" },
  lg: { icon: 32, text: "text-base" },
};

export function SyftHubLogo({ size = "md", showText = true, dark = false }: SyftHubLogoProps) {
  const s = sizes[size];
  const textColor = dark ? "text-white" : "text-gray-900";

  return (
    <span className="inline-flex items-center gap-2">
      <Image
        src="/logo.svg"
        alt="SyftHub"
        width={s.icon}
        height={s.icon}
        className="shrink-0"
      />
      {showText && (
        <span className={`font-semibold tracking-tight ${s.text} ${textColor}`}>
          SyftHub
        </span>
      )}
    </span>
  );
}
