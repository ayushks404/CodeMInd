import mongoose from "mongoose";

const queryschema = new mongoose.Schema(
  {
    projectId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Project",
      required: true,
    },
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
    },
    question: {
      type: String,
      required: true,
    },
    answer: {
      type: String,
      default: "",
    },
    sources: {
      type: Array,
      default: [],
    },
    confidence: {
      type: Number,
      default: null,
    },
    iterations: {
      type: Number,
      default: 0,
    },
  },
  { timestamps: true }
);

const Query = mongoose.model("Query", queryschema);
export default Query;
