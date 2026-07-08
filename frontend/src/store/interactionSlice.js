import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  id: null,
  hcp_name: "",
  interaction_type: "Meeting",
  date: new Date().toISOString().slice(0, 10),
  time: new Date().toTimeString().slice(0, 5),
  attendees: "",
  topics_discussed: "",
  materials_shared: [],
  samples_distributed: [],
  sentiment: "Neutral",
  outcomes: "",
  follow_up_actions: [],
  ai_suggested_followups: [],
  isLogged: false,
};

const interactionSlice = createSlice({
  name: "interaction",
  initialState,
  reducers: {
    // manual, single-field edits from the structured form
    fieldChanged: (state, action) => {
      const { field, value } = action.payload;
      state[field] = value;
    },
    // bulk patch coming back from the AI agent (/chat field_updates)
    patchApplied: (state, action) => {
      Object.entries(action.payload).forEach(([field, value]) => {
        if (field in state) state[field] = value;
      });
    },
    materialAdded: (state, action) => {
      if (!state.materials_shared.includes(action.payload)) {
        state.materials_shared.push(action.payload);
      }
    },
    sampleAdded: (state, action) => {
      if (!state.samples_distributed.includes(action.payload)) {
        state.samples_distributed.push(action.payload);
      }
    },
    followupAccepted: (state, action) => {
      const text = action.payload;
      if (!state.follow_up_actions.includes(text)) {
        state.follow_up_actions.push(text);
      }
      state.ai_suggested_followups = state.ai_suggested_followups.filter((f) => f !== text);
    },
    loggedFlagSet: (state, action) => {
      state.isLogged = action.payload;
    },
    formReset: () => initialState,
  },
});

export const {
  fieldChanged,
  patchApplied,
  materialAdded,
  sampleAdded,
  followupAccepted,
  loggedFlagSet,
  formReset,
} = interactionSlice.actions;

export default interactionSlice.reducer;
