import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { auth, isDiscordAuthConfigured, signInWithDiscord } from "@/auth";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user?.id) {
    redirect("/collection");
  }

  return (
    <div className="mx-auto max-w-xl py-8">
      <div className="rounded-3xl border border-white/10 bg-[#10101a]/95 p-7 shadow-2xl sm:p-9">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#5865F2]/20 text-[#7984ff] ring-1 ring-[#5865F2]/40">
          <LogIn className="h-6 w-6" />
        </div>

        <h1 className="mt-5 text-2xl font-extrabold tracking-tight text-white">
          Login with Discord
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-300">
          Sign in with your Discord account using the minimal{" "}
          <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-xs">
            identify
          </code>{" "}
          scope to load your Kotone Bot card inventory, COMO balance, cooldowns,
          and personalized leaderboard rank.
        </p>

        {isDiscordAuthConfigured ? (
          <form
            action={async () => {
              "use server";
              await signInWithDiscord("/collection");
            }}
            className="mt-6"
          >
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#5865F2] py-3.5 text-sm font-bold text-white shadow-[0_0_24px_-4px_rgba(88,101,242,0.8)] transition hover:bg-[#4752C4]"
            >
              Continue with Discord
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        ) : (
          <div className="mt-6 space-y-4 rounded-2xl border border-amber-400/30 bg-amber-950/20 p-5 text-sm text-amber-100">
            <div className="flex items-center gap-2 font-bold text-amber-300">
              <KeyRound className="h-4 w-4" />
              Discord OAuth Credentials Needed
            </div>
            <p className="text-xs leading-relaxed text-zinc-300">
              To enable Discord sign-in locally, add your app credentials to{" "}
              <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-amber-200">
                kotone-discord-bot/web/.env.local
              </code>
              :
            </p>
            <ol className="list-inside list-decimal space-y-1.5 text-xs text-zinc-300">
              <li>
                Open the Discord Developer Portal and select your Kotone Bot
                application.
              </li>
              <li>
                Under <strong>OAuth2 → General → Redirects</strong>, add:{" "}
                <code className="rounded bg-black/50 px-1.5 py-0.5 font-mono text-white">
                  http://localhost:3000/api/auth/callback/discord
                </code>
              </li>
              <li>
                Set{" "}
                <code className="rounded bg-black/50 px-1 py-0.5 font-mono">
                  AUTH_DISCORD_ID
                </code>{" "}
                and{" "}
                <code className="rounded bg-black/50 px-1 py-0.5 font-mono">
                  AUTH_DISCORD_SECRET
                </code>{" "}
                in <code className="font-mono">.env.local</code> and restart the
                dev server.
              </li>
            </ol>
          </div>
        )}

        <div className="mt-6 flex items-center justify-between border-t border-white/10 pt-5 text-xs text-zinc-400">
          <span className="inline-flex items-center gap-1.5 text-emerald-300">
            <ShieldCheck className="h-4 w-4" />
            JWT Cookie Session (No DB schema changes)
          </span>
          <Link href="/leaderboard" className="text-[#ff9bb0] hover:underline">
            Browse Leaderboards →
          </Link>
        </div>
      </div>
    </div>
  );
}
