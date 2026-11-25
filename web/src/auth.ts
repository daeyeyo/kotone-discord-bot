import NextAuth, { type DefaultSession } from "next-auth";
import Discord from "next-auth/providers/discord";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      username?: string | null;
    } & DefaultSession["user"];
  }
}

const discordClientId = process.env.AUTH_DISCORD_ID?.trim() ?? "";
const discordClientSecret = process.env.AUTH_DISCORD_SECRET?.trim() ?? "";

export const isDiscordAuthConfigured = Boolean(
  discordClientId && discordClientSecret
);

const nextAuth = isDiscordAuthConfigured
  ? NextAuth({
      providers: [
        Discord({
          clientId: discordClientId,
          clientSecret: discordClientSecret,
          authorization: {
            params: {
              scope: "identify",
            },
          },
        }),
      ],
      session: {
        strategy: "jwt",
      },
      pages: {
        signIn: "/login",
      },
      callbacks: {
        jwt({ token, profile }) {
          if (profile) {
            const discordProfile = profile as {
              id?: string;
              username?: string;
              global_name?: string | null;
              avatar?: string | null;
            };
            if (discordProfile.id) {
              token.discordId = discordProfile.id;
            }
            if (discordProfile.username) {
              token.username = discordProfile.username;
            }
            if (discordProfile.global_name) {
              token.name = discordProfile.global_name;
            }
            if (discordProfile.id && discordProfile.avatar) {
              const ext = discordProfile.avatar.startsWith("a_")
                ? "gif"
                : "png";
              token.picture = `https://cdn.discordapp.com/avatars/${discordProfile.id}/${discordProfile.avatar}.${ext}?size=256`;
            }
          }
          return token;
        },
        session({ session, token }) {
          if (session.user) {
            session.user.id =
              (typeof token.discordId === "string" ? token.discordId : "") ||
              token.sub ||
              "";
            session.user.username =
              typeof token.username === "string" ? token.username : null;
          }
          return session;
        },
      },
    })
  : null;

export const handlers = nextAuth?.handlers ?? {
  GET: () =>
    Response.json(
      {
        error:
          "Discord OAuth is not configured yet. Set AUTH_DISCORD_ID and AUTH_DISCORD_SECRET in web/.env.local.",
      },
      { status: 503 }
    ),
  POST: () =>
    Response.json(
      {
        error:
          "Discord OAuth is not configured yet. Set AUTH_DISCORD_ID and AUTH_DISCORD_SECRET in web/.env.local.",
      },
      { status: 503 }
    ),
};

export async function auth() {
  if (!nextAuth) return null;
  try {
    return await nextAuth.auth();
  } catch {
    return null;
  }
}

export async function signInWithDiscord(redirectTo = "/collection") {
  if (!nextAuth) {
    throw new Error("Discord OAuth is not configured.");
  }
  return nextAuth.signIn("discord", { redirectTo });
}

export async function signOutUser(redirectTo = "/") {
  if (!nextAuth) return;
  return nextAuth.signOut({ redirectTo });
}
