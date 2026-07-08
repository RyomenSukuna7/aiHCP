import React from "react";
import { useDispatch, useSelector } from "react-redux";
import { fieldChanged, followupAccepted } from "../store/interactionSlice";

const INTERACTION_TYPES = ["Meeting", "Call", "Email", "Conference"];
const SENTIMENTS = [
  { key: "Positive", emoji: "🙂" },
  { key: "Neutral", emoji: "😐" },
  { key: "Negative", emoji: "🙁" },
];

export default function LogInteractionForm() {
  const state = useSelector((s) => s.interaction);
  const dispatch = useDispatch();

  const set = (field) => (e) =>
    dispatch(fieldChanged({ field, value: e.target.value }));

  return (
    <section className="card form-card">
      <h2 className="card-heading">Interaction Details</h2>

      <div className="grid-2">
        <Field label="HCP Name">
          <input
            className="input"
            placeholder="Search or select HCP..."
            value={state.hcp_name}
            onChange={set("hcp_name")}
          />
        </Field>

        <Field label="Interaction Type">
          <select
            className="input"
            value={state.interaction_type}
            onChange={set("interaction_type")}
          >
            {INTERACTION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Date">
          <input
            type="date"
            className="input"
            value={state.date}
            onChange={set("date")}
          />
        </Field>

        <Field label="Time">
          <input
            type="time"
            className="input"
            value={state.time}
            onChange={set("time")}
          />
        </Field>
      </div>

      <Field label="Attendees">
        <input
          className="input"
          placeholder="Enter names or search..."
          value={state.attendees}
          onChange={set("attendees")}
        />
      </Field>

      <Field label="Topics Discussed">
        <textarea
          className="input textarea"
          placeholder="Enter key discussion points..."
          value={state.topics_discussed}
          onChange={set("topics_discussed")}
        />
      </Field>

      <div className="section-label">Materials Shared / Samples Distributed</div>

      <ChipList
        title="Materials Shared"
        items={state.materials_shared}
        empty="No materials added."
      />
      <ChipList
        title="Samples Distributed"
        items={state.samples_distributed}
        empty="No samples added."
      />

      <div className="section-label">Observed / Inferred HCP Sentiment</div>
      <div className="sentiment-row">
        {SENTIMENTS.map((s) => (
          <label key={s.key} className="sentiment-option">
            <input
              type="radio"
              name="sentiment"
              checked={state.sentiment === s.key}
              onChange={() => dispatch(fieldChanged({ field: "sentiment", value: s.key }))}
            />
            <span className="sentiment-emoji">{s.emoji}</span>
            <span>{s.key}</span>
          </label>
        ))}
      </div>

      <Field label="Outcomes">
        <textarea
          className="input textarea"
          placeholder="Key outcomes or agreements..."
          value={state.outcomes}
          onChange={set("outcomes")}
        />
      </Field>

      <Field label="Follow-up Actions">
        <textarea
          className="input textarea"
          placeholder="Enter next steps or tasks..."
          value={state.follow_up_actions.join("\n")}
          onChange={(e) =>
            dispatch(
              fieldChanged({
                field: "follow_up_actions",
                value: e.target.value.split("\n").filter(Boolean),
              })
            )
          }
        />
      </Field>

      {state.ai_suggested_followups.length > 0 && (
        <div className="ai-followups">
          <div className="ai-followups-title">AI Suggested Follow-ups:</div>
          {state.ai_suggested_followups.map((f) => (
            <button
              key={f}
              className="followup-chip"
              onClick={() => dispatch(followupAccepted(f))}
            >
              + {f}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function ChipList({ title, items, empty }) {
  return (
    <div className="chip-block">
      <div className="chip-block-title">{title}</div>
      {items.length === 0 ? (
        <div className="chip-empty">{empty}</div>
      ) : (
        <div className="chip-row">
          {items.map((i) => (
            <span key={i} className="chip">
              {i}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
