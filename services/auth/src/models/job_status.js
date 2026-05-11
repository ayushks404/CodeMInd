import mongoose from "mongoose";

const jobStatusSchema = new mongoose.Schema(
  {
    jobId: {
      type: String,
      required: true,
      unique: true,
    },
    type: {
      type: String,
      enum: ["query", "index"],
      required: true,
    },
    status: {
      type: String,
      enum: [
        "queued",
        "processing",
        "completed",
        "failed",
        "failed_final",
      ],
      default: "queued",
    },
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
    },
    projectId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Project",
      required: true,
    },
    // For query jobs — filled when completed
    answer:     { type: String,  default: null },
    confidence: { type: Number,  default: null },
    sources:    { type: Array,   default: [] },
    trace:      { type: Array,   default: [] },

    // For failed jobs
    error:   { type: String, default: null },
    retries: { type: Number, default: 0 },

    completedAt: { type: Date, default: null },
  },
  { timestamps: true }
);

const JobStatus = mongoose.model("JobStatus", jobStatusSchema);
export default JobStatus;