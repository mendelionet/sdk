/**
 * Generate speech with a system voice and save it to disk.
 *
 *   MENDELIO_VOICE_API_KEY=mv_live_… npx tsx examples/node-generate.ts
 */
import { writeFileSync } from "node:fs";
import { MendelioVoice } from "mendelio-voice";

const client = new MendelioVoice();

const { generation, audio } = await client.speak({
  text: "Ahoj! Tohle je ukázka Mendelio Voice.",
  format: "mp3",
});

writeFileSync("out.mp3", audio);
console.log(`Saved out.mp3 (${audio.byteLength} bytes), generation ${generation.id}.`);
