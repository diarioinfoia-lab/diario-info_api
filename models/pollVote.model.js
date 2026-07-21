const mongoose = require("mongoose");
const { Schema } = mongoose;

const PollVoteSchema = new Schema(
  {
        poll: { type: Schema.Types.ObjectId, ref: "Poll", required: true },
        optionIndex: { type: Number, required: true },
        voterHash: { type: String, required: true },
        ipHash: { type: String, required: true },
        ipSubnetHash: { type: String },
        region: { type: String, default: null },
        userAgentSummary: {
                browser: String,
                os: String,
                deviceType: String,
        },
        referrer: { type: String, default: null },
        flagged: { type: Boolean, default: false },
        flagReason: { type: String, default: null },
  },
  { timestamps: true }
  );

PollVoteSchema.index({ poll: 1, voterHash: 1 }, { unique: true });
PollVoteSchema.index({ poll: 1, ipHash: 1, createdAt: -1 });
PollVoteSchema.index({ poll: 1, ipSubnetHash: 1, createdAt: -1 });

const PollVote = mongoose.models.PollVote || mongoose.model("PollVote", PollVoteSchema);
module.exports = PollVote;
