import { SyftHubLogo } from "@/components/brand/syfthub-logo";

interface FooterProps {
  dark?: boolean;
}

export function Footer({ dark = false }: FooterProps) {
  const bg = dark ? "bg-gray-950 border-gray-800" : "bg-white border-gray-100";
  const textMuted = dark ? "text-gray-500" : "text-gray-400";

  return (
    <footer className={`border-t py-10 ${bg}`}>
      <div className={`mx-auto flex max-w-5xl flex-col items-center justify-between gap-4 px-6 sm:flex-row ${textMuted}`}>
        <SyftHubLogo size="sm" dark={dark} />
        <p className="text-xs">
          &copy; {new Date().getFullYear()} SyftHub. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
