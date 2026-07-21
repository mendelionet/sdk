/**
 * Verify Mendelio Voice webhooks in an Express endpoint. Use the RAW body — a re-serialized object
 * would change key order and break the HMAC.
 */
import express from "express";
import { constructEvent, WebhookVerificationError } from "mendelio-voice";

const app = express();
const SECRET = process.env.MENDELIO_VOICE_WEBHOOK_SECRET!;

app.post("/webhooks/voice", express.raw({ type: "application/json" }), async (req, res) => {
  try {
    const event = await constructEvent(req.body.toString("utf8"), req.headers, SECRET);
    // Deduplicate by event.id — deliveries are at-least-once.
    console.log(`event ${event.id}: ${event.type}`);
    res.sendStatus(200);
  } catch (err) {
    if (err instanceof WebhookVerificationError) return res.sendStatus(400);
    throw err;
  }
});

app.listen(3000, () => console.log("listening on :3000"));
