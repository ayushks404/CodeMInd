import mongoose from "mongoose";

const jobStatusSchema = new mongoose.Schema(
  {
    jobId:     { type: String, required: true, unique: true },
    type:      { type: String, enum: ["query", "index"], required: true },
    status: {
      type: String,
      enum: ["queued", "processing", "completed", "failed", "failed_final"],
      default: "queued",
    },
    userId:    { type: mongoose.Schema.Types.ObjectId, ref: "User", required: true },
    projectId: { type: mongoose.Schema.Types.ObjectId, ref: "Project", required: true },

    // FIX: cacheKey was being saved by query_controllers but didn't exist in the schema.
    // query_worker reads job:cache_key:{jobId} from Redis to write the result back to cache.
    // Storing it here too gives a fallback and makes the job record self-contained.
    cacheKey: { type: String, default: null },

    answer:     { type: String, default: null },
    confidence: { type: Number, default: null },
    sources:    { type: Array,  default: [] },
    trace:      { type: Array,  default: [] },
    error:      { type: String, default: null },
    retries:    { type: Number, default: 0 },
    completedAt:{ type: Date,   default: null },
  },
  { timestamps: true }
);

export default mongoose.model("JobStatus", jobStatusSchema);