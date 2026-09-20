"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BrandSymbol } from "@/components/branding/BrandLogo";
import { CloseIcon, MenuIcon } from "@/components/landing/icons";

const NAV_LINKS = [
  { href: "#accueil", label: "Accueil" },
  { href: "#fonctionnalites", label: "Fonctionnalités" },
  { href: "#solutions", label: "Solutions" },
  { href: "#a-propos", label: "À propos" },
];

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 8);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 transition-colors duration-300 ${
        scrolled
          ? "border-b border-slate-200/80 bg-white/85 backdrop-blur-md"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <a href="#accueil" className="flex items-center gap-2">
          <BrandSymbol className="h-8 w-8" priority />
          <span className="text-lg font-bold text-brand-text">EduLinkage</span>
        </a>

        <nav aria-label="Navigation principale" className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-slate-600 transition hover:text-brand-blue"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/login"
            className="rounded-lg px-4 py-2 text-sm font-semibold text-brand-text transition hover:bg-slate-100"
          >
            Se connecter
          </Link>
          <a
            href="#contact"
            className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
          >
            Demander une démo
          </a>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-controls="landing-mobile-menu"
          aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-brand-text md:hidden"
        >
          {menuOpen ? <CloseIcon /> : <MenuIcon />}
        </button>
      </div>

      {menuOpen && (
        <div id="landing-mobile-menu" className="border-t border-slate-200 bg-white px-4 py-4 md:hidden">
          <nav aria-label="Navigation mobile" className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                {link.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2 border-t border-slate-100 pt-3">
              <Link
                href="/login"
                onClick={() => setMenuOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2.5 text-center text-sm font-semibold text-brand-text"
              >
                Se connecter
              </Link>
              <a
                href="#contact"
                onClick={() => setMenuOpen(false)}
                className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-center text-sm font-semibold text-white"
              >
                Demander une démo
              </a>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
