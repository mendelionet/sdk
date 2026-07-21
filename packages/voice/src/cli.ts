#!/usr/bin/env node
import { MendelioVoice } from "./client.js";
import { clearCredentials, readCredentials } from "./credentials.js";
import { deviceLogin } from "./login.js";

/** Tiny zero-dependency CLI: login | logout | whoami. */
async function main(argv: string[]): Promise<number> {
  const command = argv[0];
  switch (command) {
    case "login": {
      const { keyPrefix } = await deviceLogin({
        onCode: ({ userCode, verificationUriComplete }) => {
          console.log(`\n  Open:  ${verificationUriComplete}`);
          console.log(`  Code:  ${userCode}\n`);
          console.log("  Waiting for you to approve in the browser…");
        },
      });
      console.log(`\n✓ Logged in. Key ${keyPrefix}… saved to ~/.config/mendelio/credentials.json`);
      return 0;
    }
    case "logout": {
      clearCredentials();
      console.log("✓ Logged out.");
      return 0;
    }
    case "whoami": {
      const creds = readCredentials();
      if (!creds && !process.env.MENDELIO_VOICE_API_KEY) {
        console.error("Not logged in. Run `mendelio-voice login`.");
        return 1;
      }
      const balance = await new MendelioVoice().balance.get();
      console.log(`Key: ${creds?.key_prefix ?? "(from MENDELIO_VOICE_API_KEY)"}…`);
      console.log(`Balance: ${balance.available} available / ${balance.total} total (audio seconds).`);
      return 0;
    }
    default:
      console.log("Usage: mendelio-voice <login | logout | whoami>");
      return command ? 1 : 0;
  }
}

main(process.argv.slice(2))
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
