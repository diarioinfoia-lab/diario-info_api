const express = require("express");
const router = express.Router();
const pollController = require("../controllers/poll.controller.js");
const checkAuth = require("../middlewares/check-auth.js");

router.post("/polls", checkAuth, pollController.createPoll);
router.get("/polls", [], pollController.getPolls);
router.get("/poll/:id", [], pollController.getPoll);
router.put("/poll/:id", checkAuth, pollController.updatePoll);
router.delete("/poll/:id", checkAuth, pollController.deletePoll);
router.post("/poll/:id/activate", checkAuth, pollController.activatePoll);
router.post("/poll/:id/close", checkAuth, pollController.closePoll);
router.get("/poll/:id/audit", checkAuth, pollController.getPollAudit);

router.post("/poll/:id/vote", [], pollController.vote);

module.exports = router;
