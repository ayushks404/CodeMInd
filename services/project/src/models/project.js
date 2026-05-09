import mongoose from "mongoose";

const projectschema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: true,
    },
    repourl: {
      type: String,
      required: true,
    },
    owner: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
    },
    // FIX: field was named `index` in schema but `indexed` everywhere else
    // Renamed to `indexed` to match the rest of the codebase
    indexed: {
      type: Boolean,
      default: false,
    },
    indexedAt: {
      type: Date,
      default: null,
    },
    fileCount: {
      type: Number,
      default: 0,
    },
    chunkCount: {
      type: Number,
      default: 0,
    },
  },
  { timestamps: true }
);

export default mongoose.model("Project", projectschema);
