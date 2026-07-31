(function (root, factory) {
    var api = factory();
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.DoomArenaElevenAgents = api;
    }
})(typeof window !== "undefined" ? window : null, function () {
    "use strict";

    var DEFAULT_COOLDOWN_MS = 2500;
    var DEFAULT_CONTEXT_INTERVAL_MS = 10000;
    var DEFAULT_CUE_MAX_AGE_MS = 5000;
    var HEAVY_DAMAGE_THRESHOLD = 30;
    var CRITICAL_HEALTH = 40;

    function numberValue(value, fallback) {
        var parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function optionalNonnegativeNumber(value) {
        var parsed;
        if (value === null || value === undefined || value === "") {
            return null;
        }
        parsed = Number(value);
        return Number.isFinite(parsed) ? Math.max(0, parsed) : null;
    }

    function truthy(value) {
        return value === true || value === 1 || value === "1" || value === "true";
    }

    function compactText(value, limit) {
        var text = String(value || "").replace(/\s+/g, " ").trim();
        if (!limit || text.length <= limit) {
            return text;
        }
        return text.slice(0, Math.max(1, limit - 1)).trimEnd() + "…";
    }

    function friendlyEngagement(value) {
        var normalized = String(value || "").trim().toLowerCase();
        return {
            engage_if_visible: "fight if the opponent becomes visible",
            avoid_until_target: "avoid combat until reaching the target",
            hold_fire: "hold fire",
            force_fight: "force an engagement"
        }[normalized] || compactText(normalized.replace(/_/g, " "), 90);
    }

    function friendlyIntent(value) {
        var normalized = String(value || "").trim().toLowerCase();
        return {
            engage_opponent: "engage the opponent",
            strafe_attack: "circle and attack the opponent",
            search: "search the arena",
            hold: "hold position"
        }[normalized] || compactText(normalized.replace(/_/g, " "), 100);
    }

    function latestPlan(intentRows, participantId, player, nowMs) {
        var rows = (intentRows || []).filter(function (row) {
            return row && row.participant_id === participantId;
        });
        var currentIntentId = String(player && player.intent_id || "");
        var row = rows.find(function (candidate) {
            return currentIntentId && candidate.intent_id === currentIntentId;
        });
        var issuedAt;

        if (!row && rows.length) {
            row = rows.slice().sort(function (left, right) {
                return numberValue(left.issued_at_ms, 0) - numberValue(right.issued_at_ms, 0);
            })[rows.length - 1];
        }
        if (!row) {
            return null;
        }

        issuedAt = numberValue(row.issued_at_ms, 0);
        return {
            decision_number: numberValue(row.sequence_number, null),
            objective: compactText(
                row.plan_objective || row.strategy_objective || friendlyIntent(row.intent),
                150
            ),
            engagement: friendlyEngagement(row.plan_engagement_policy || row.fire_policy),
            reason: compactText(row.plan_reasoning || row.strategy_reasoning, 180),
            battle_note: compactText(row.plan_summary, 120),
            status: currentIntentId && row.intent_id === currentIntentId
                ? String(player.intent_status || "active")
                : "latest",
            active_for_seconds: issuedAt > 0
                ? Math.max(0, Math.floor((nowMs - issuedAt) / 1000))
                : null
        };
    }

    function participantSnapshot(participantId, player, name, pickupCounts, intentRows, nowMs) {
        var counts = pickupCounts || { health: 0, shotgun: 0 };
        var readyWeapon = String(player && player.ready_weapon || "").toLowerCase();
        var hasShotgun = counts.shotgun > 0 || readyWeapon === "2" || readyWeapon.indexOf("shotgun") !== -1;
        return {
            id: participantId,
            name: compactText(name, 48),
            health: optionalNonnegativeNumber(player && player.health),
            alive: !player || player.alive === undefined ? null : truthy(player.alive),
            damage_dealt: optionalNonnegativeNumber(player && player.damage_dealt),
            equipment: hasShotgun ? ["shotgun"] : [],
            health_packs_collected: Math.max(0, numberValue(counts.health, 0)),
            opponent_visible: truthy(player && player.line_of_sight),
            plan: latestPlan(intentRows, participantId, player || {}, nowMs)
        };
    }

    function distanceBand(player1, player2) {
        var x1 = numberValue(player1 && player1.x, NaN);
        var y1 = numberValue(player1 && player1.y, NaN);
        var x2 = numberValue(player2 && player2.x, NaN);
        var y2 = numberValue(player2 && player2.y, NaN);
        var distance;
        if (![x1, y1, x2, y2].every(Number.isFinite)) {
            return "unknown";
        }
        distance = Math.hypot(x1 - x2, y1 - y2);
        if (distance < 280) {
            return "close";
        }
        if (distance < 720) {
            return "medium";
        }
        return "long";
    }

    function planSignature(plan) {
        if (!plan) {
            return "";
        }
        // A fresh sequence number is not necessarily a fresh idea. Comment on
        // meaningful tactical changes instead of narrating every MCP refresh.
        return [plan.objective, plan.engagement, plan.reason].join("|");
    }

    function publicSnapshot(snapshot) {
        var copy = Object.assign({}, snapshot);
        delete copy.run_id;
        return copy;
    }

    function buildSnapshot(input, nowMs) {
        var player1 = input.player1 || {};
        var player2 = input.player2 || {};
        var participants = {
            player_1: participantSnapshot(
                "player_1",
                player1,
                input.player1Name || "Player 1",
                input.pickups && input.pickups.player_1,
                input.intentRows,
                nowMs
            ),
            player_2: participantSnapshot(
                "player_2",
                player2,
                input.player2Name || "Player 2",
                input.pickups && input.pickups.player_2,
                input.intentRows,
                nowMs
            )
        };
        return {
            schema_version: 1,
            message_type: "match_snapshot",
            run_id: compactText(input.runId, 80),
            benchmark: {
                current_round: Math.max(1, numberValue(input.round, 1)),
                total_rounds: Math.max(1, numberValue(input.totalRounds, 1)),
                scenario: compactText(input.scenario || "Blind spawn", 80),
                score: {
                    player_1: Math.max(0, numberValue(input.score && input.score.player_1, 0)),
                    player_2: Math.max(0, numberValue(input.score && input.score.player_2, 0))
                }
            },
            match: {
                phase: compactText(input.phase || "waiting", 40),
                elapsed_seconds: Math.max(0, Math.floor(numberValue(input.elapsedSeconds, 0))),
                winner: compactText(input.winner, 48),
                terminal_reason: compactText(input.terminalReason, 80),
                distance: distanceBand(player1, player2),
                combat_active: truthy(player1.line_of_sight) || truthy(player2.line_of_sight)
            },
            players: participants
        };
    }

    function cue(type, actor, significance, facts, extra) {
        return Object.assign({
            type: type,
            actor: actor || "",
            significance: significance || "medium",
            facts: facts.filter(Boolean)
        }, extra || {});
    }

    function cuePriority(event) {
        return {
            round_end: 100,
            critical_health: 80,
            weapon_pickup: 70,
            heavy_damage: 65,
            first_contact: 60,
            match_start: 55,
            broadcast_join: 50,
            health_pickup: 40,
            plan_change: 30
        }[event && event.type] || 10;
    }

    function cueDelayMs(event, fallback) {
        return {
            round_end: 0,
            critical_health: 0,
            weapon_pickup: 200,
            heavy_damage: 350,
            first_contact: 500,
            match_start: 0,
            broadcast_join: 500,
            health_pickup: 900,
            plan_change: 2200
        }[event && event.type] ?? fallback;
    }

    function cueMaxAgeMs(event) {
        return {
            round_end: 15000,
            critical_health: 7000,
            weapon_pickup: 7000,
            heavy_damage: 5000,
            first_contact: 5000,
            match_start: 15000,
            health_pickup: 4500,
            plan_change: 4000
        }[event && event.type] || DEFAULT_CUE_MAX_AGE_MS;
    }

    function matchIntroductionCue(snapshot) {
        var p1 = snapshot.players.player_1;
        var p2 = snapshot.players.player_2;
        return cue("match_start", "", "major", [
            "Open with: In the Rootly Doom Agent Areeennaaaa",
            "Player 1 is " + p1.name,
            "Player 2 is " + p2.name,
            "Round " + snapshot.benchmark.current_round + " of " + snapshot.benchmark.total_rounds,
            "Introduce both competitors before calling the action"
        ]);
    }

    function healthLabel(value) {
        return value === null ? "unknown" : String(value);
    }

    function broadcastJoinCue(snapshot) {
        var p1 = snapshot.players.player_1;
        var p2 = snapshot.players.player_2;
        return cue("broadcast_join", "", "medium", [
            "Join the match already in progress",
            p1.name + " has " + healthLabel(p1.health) + " health",
            p2.name + " has " + healthLabel(p2.health) + " health"
        ]);
    }

    function chooseCue(previous, current) {
        var p1 = current.players.player_1;
        var p2 = current.players.player_2;
        var old1;
        var old2;
        var damageTaken1;
        var damageTaken2;
        var winnerName;
        var resultFact;

        if (!previous || previous.run_id !== current.run_id) {
            if (current.match.phase === "combat") {
                return matchIntroductionCue(current);
            }
            return null;
        }

        old1 = previous.players.player_1;
        old2 = previous.players.player_2;
        if (previous.match.phase !== "combat" && current.match.phase === "combat") {
            return matchIntroductionCue(current);
        }
        if (previous.match.phase !== "finished" && current.match.phase === "finished") {
            winnerName = current.match.winner === "player_1"
                ? p1.name
                : current.match.winner === "player_2"
                    ? p2.name
                    : "draw";
            resultFact = current.match.terminal_reason === "player_1_dead"
                ? p1.name + " was eliminated"
                : current.match.terminal_reason === "player_2_dead"
                    ? p2.name + " was eliminated"
                    : current.match.terminal_reason.indexOf("timeout") !== -1
                        ? "The round reached its time limit"
                        : "The round is complete";
            return cue("round_end", winnerName, "critical", [
                "Winner: " + winnerName,
                "Final health: " + p1.name + " " + healthLabel(p1.health) + ", " + p2.name + " " + healthLabel(p2.health),
                resultFact
            ]);
        }

        if (old1.health !== null && p1.health !== null && old1.health > CRITICAL_HEALTH && p1.health <= CRITICAL_HEALTH) {
            return cue("critical_health", p1.name, "major", [
                p1.name + " has " + p1.health + " health remaining",
                !previous.match.combat_active && current.match.combat_active ? "This is first contact" : ""
            ]);
        }
        if (old2.health !== null && p2.health !== null && old2.health > CRITICAL_HEALTH && p2.health <= CRITICAL_HEALTH) {
            return cue("critical_health", p2.name, "major", [
                p2.name + " has " + p2.health + " health remaining",
                !previous.match.combat_active && current.match.combat_active ? "This is first contact" : ""
            ]);
        }

        if (p1.equipment.indexOf("shotgun") !== -1 && old1.equipment.indexOf("shotgun") === -1) {
            return cue("weapon_pickup", p1.name, "major", [p1.name + " acquired the shotgun"]);
        }
        if (p2.equipment.indexOf("shotgun") !== -1 && old2.equipment.indexOf("shotgun") === -1) {
            return cue("weapon_pickup", p2.name, "major", [p2.name + " acquired the shotgun"]);
        }

        damageTaken1 = old1.health === null || p1.health === null ? 0 : Math.max(0, old1.health - p1.health);
        damageTaken2 = old2.health === null || p2.health === null ? 0 : Math.max(0, old2.health - p2.health);
        if (damageTaken1 >= HEAVY_DAMAGE_THRESHOLD || damageTaken2 >= HEAVY_DAMAGE_THRESHOLD) {
            return cue("heavy_damage", damageTaken1 >= damageTaken2 ? p1.name : p2.name, "major", [
                p1.name + " has " + p1.health + " health",
                p2.name + " has " + p2.health + " health",
                "The fighters are at " + current.match.distance + " range",
                !previous.match.combat_active && current.match.combat_active ? "This is first contact" : ""
            ]);
        }

        if (!previous.match.combat_active && current.match.combat_active) {
            return cue("first_contact", "", "major", [
                p1.name + " and " + p2.name + " can now see each other",
                "They are at " + current.match.distance + " range"
            ]);
        }

        if (p1.health_packs_collected > old1.health_packs_collected) {
            return cue("health_pickup", p1.name, "medium", [
                p1.name + " collected a health pack",
                p1.health === null ? "" : "Current health: " + p1.health
            ]);
        }
        if (p2.health_packs_collected > old2.health_packs_collected) {
            return cue("health_pickup", p2.name, "medium", [
                p2.name + " collected a health pack",
                p2.health === null ? "" : "Current health: " + p2.health
            ]);
        }

        if (planSignature(old1.plan) !== planSignature(p1.plan) && p1.plan) {
            return cue("plan_change", p1.name, "medium", [
                p1.name + " now plans to " + p1.plan.objective,
                p1.plan.reason ? "Reason: " + p1.plan.reason : "",
                p1.plan.engagement ? "Engagement: " + p1.plan.engagement : ""
            ], { plan: p1.plan });
        }
        if (planSignature(old2.plan) !== planSignature(p2.plan) && p2.plan) {
            return cue("plan_change", p2.name, "medium", [
                p2.name + " now plans to " + p2.plan.objective,
                p2.plan.reason ? "Reason: " + p2.plan.reason : "",
                p2.plan.engagement ? "Engagement: " + p2.plan.engagement : ""
            ], { plan: p2.plan });
        }
        return null;
    }

    function sampleRateFromFormat(format) {
        var match = String(format || "pcm_16000").match(/(\d{4,6})/);
        return match ? Number(match[1]) : 16000;
    }

    function decodeBase64Pcm(base64) {
        var binary = atob(base64);
        var bytes = new Uint8Array(binary.length);
        var samples;
        var index;
        for (index = 0; index < binary.length; index++) {
            bytes[index] = binary.charCodeAt(index);
        }
        samples = new Float32Array(Math.floor(bytes.length / 2));
        for (index = 0; index < samples.length; index++) {
            var value = bytes[index * 2] | (bytes[index * 2 + 1] << 8);
            if (value >= 0x8000) {
                value -= 0x10000;
            }
            samples[index] = value / 0x8000;
        }
        return samples;
    }

    function Commentator(options) {
        this.options = options || {};
        this.socket = null;
        this.audioContext = null;
        this.gainNode = null;
        this.nextAudioTime = 0;
        this.sampleRate = 16000;
        this.enabled = false;
        this.ready = false;
        this.speaking = false;
        this.lastSnapshot = null;
        this.lastContextAt = 0;
        this.lastCueAt = 0;
        this.pendingCue = null;
        this.pendingCueTimer = 0;
        this.readyWaiters = [];
        this.introduction = null;
        this.introductionPromise = null;
        this.introducingRunId = "";
        this.introducedRunId = "";
        this.enablePromise = null;
        this.audioOwnershipPromise = null;
        this.audioOwnershipRelease = null;
        this.audioGeneration = 0;
        this.audioIdleTimer = 0;
        this.cooldownMs = this.options.cooldownMs || DEFAULT_COOLDOWN_MS;
        this.contextIntervalMs = this.options.contextIntervalMs || DEFAULT_CONTEXT_INTERVAL_MS;
    }

    Commentator.prototype.status = function (message, state) {
        if (typeof this.options.onStatus === "function") {
            this.options.onStatus(message, state || "idle");
        }
    };

    Commentator.prototype.setVolume = function (value) {
        var volume = Math.max(0, Math.min(1, numberValue(value, 0.8)));
        if (this.gainNode) {
            this.gainNode.gain.value = volume;
        }
    };

    Commentator.prototype.prepareAudio = function () {
        var AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            this.status("Live audio is not supported in this browser", "error");
            return Promise.reject(new Error("AudioContext unavailable"));
        }
        this.audioContext = this.audioContext || new AudioContextClass();
        if (!this.gainNode) {
            this.gainNode = this.audioContext.createGain();
            this.gainNode.connect(this.audioContext.destination);
        }
        this.setVolume(this.options.volume === undefined ? 0.8 : this.options.volume);
        return this.audioContext.resume();
    };

    Commentator.prototype.acquireAudioOwnership = function () {
        var self = this;
        var pending;
        var tracked;

        if (this.audioOwnershipRelease) {
            return Promise.resolve();
        }
        if (this.audioOwnershipPromise) {
            return this.audioOwnershipPromise;
        }
        if (
            typeof navigator === "undefined" ||
            !navigator.locks ||
            typeof navigator.locks.request !== "function"
        ) {
            return Promise.resolve();
        }

        pending = new Promise(function (resolve, reject) {
            navigator.locks.request(
                "rootly-doom-arena-shoutcaster",
                { mode: "exclusive", ifAvailable: true },
                function (lock) {
                    if (!lock) {
                        reject(new Error("Shoutcaster is already active in another arena tab"));
                        return;
                    }
                    return new Promise(function (release) {
                        self.audioOwnershipRelease = release;
                        resolve();
                    });
                }
            ).catch(reject);
        });
        tracked = pending.then(
            function () {
                if (self.audioOwnershipPromise === tracked) {
                    self.audioOwnershipPromise = null;
                }
            },
            function (error) {
                if (self.audioOwnershipPromise === tracked) {
                    self.audioOwnershipPromise = null;
                }
                throw error;
            }
        );
        this.audioOwnershipPromise = tracked;
        return this.audioOwnershipPromise;
    };

    Commentator.prototype.releaseAudioOwnership = function () {
        if (this.audioOwnershipRelease) {
            this.audioOwnershipRelease();
            this.audioOwnershipRelease = null;
        }
        this.audioOwnershipPromise = null;
    };

    Commentator.prototype.expectIntroduction = function (runId) {
        runId = compactText(runId, 80);
        if (!runId || this.introducedRunId === runId) {
            return;
        }
        this.introducingRunId = runId;
        if (
            this.pendingCue &&
            (this.pendingCue.event.type === "match_start" || this.pendingCue.event.type === "broadcast_join")
        ) {
            this.pendingCue = null;
        }
    };

    Commentator.prototype.enable = function () {
        var self = this;
        if (this.enabled && this.socket) {
            return this.waitUntilReady(15000);
        }
        if (this.enablePromise) {
            return this.enablePromise;
        }
        this.enabled = true;
        this.status("Connecting shoutcaster…", "connecting");
        this.enablePromise = this.acquireAudioOwnership()
            .then(function () {
                return self.prepareAudio();
            })
            .then(function () {
                return fetch(self.options.signedUrlEndpoint || "/api/arena/commentator/signed-url", { cache: "no-store" });
            })
            .then(function (response) {
                return response.json().then(function (payload) {
                    if (!response.ok || !payload.signed_url) {
                        throw new Error(payload.error || "Unable to obtain ElevenAgents connection");
                    }
                    return payload.signed_url;
                });
            })
            .then(function (signedUrl) {
                self.openSocket(signedUrl);
                return self.waitUntilReady(15000);
            })
            .then(function () {
                self.enablePromise = null;
            })
            .catch(function (error) {
                self.enablePromise = null;
                self.enabled = false;
                self.releaseAudioOwnership();
                self.status(error.message || "Unable to connect shoutcaster", "error");
                throw error;
            });
        return this.enablePromise;
    };

    Commentator.prototype.disable = function () {
        this.enabled = false;
        this.ready = false;
        this.speaking = false;
        this.pendingCue = null;
        if (this.pendingCueTimer) {
            window.clearTimeout(this.pendingCueTimer);
            this.pendingCueTimer = 0;
        }
        this.rejectReadyWaiters(new Error("Shoutcaster disabled"));
        this.rejectIntroduction(new Error("Shoutcaster disabled"));
        if (this.audioIdleTimer) {
            window.clearTimeout(this.audioIdleTimer);
            this.audioIdleTimer = 0;
        }
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        this.enablePromise = null;
        this.introducingRunId = "";
        this.releaseAudioOwnership();
        this.status("Shoutcaster off", "idle");
    };

    Commentator.prototype.waitUntilReady = function (timeoutMs) {
        var self = this;
        if (this.ready) {
            return Promise.resolve();
        }
        return new Promise(function (resolve, reject) {
            var waiter = { resolve: resolve, reject: reject, timer: 0 };
            waiter.timer = window.setTimeout(function () {
                self.readyWaiters = self.readyWaiters.filter(function (candidate) {
                    return candidate !== waiter;
                });
                reject(new Error("Timed out waiting for the ElevenAgents handshake"));
            }, timeoutMs || 15000);
            self.readyWaiters.push(waiter);
        });
    };

    Commentator.prototype.resolveReadyWaiters = function () {
        var waiters = this.readyWaiters.splice(0);
        waiters.forEach(function (waiter) {
            window.clearTimeout(waiter.timer);
            waiter.resolve();
        });
    };

    Commentator.prototype.rejectReadyWaiters = function (error) {
        var waiters = this.readyWaiters.splice(0);
        waiters.forEach(function (waiter) {
            window.clearTimeout(waiter.timer);
            waiter.reject(error);
        });
    };

    Commentator.prototype.openSocket = function (signedUrl) {
        var self = this;
        var previousSocket = this.socket;
        var socket = new WebSocket(signedUrl);
        this.socket = socket;
        if (previousSocket) {
            previousSocket.close();
        }
        socket.addEventListener("open", function () {
            if (self.socket !== socket) {
                return;
            }
            self.status("Warming up the shoutcaster…", "connecting");
            socket.send(JSON.stringify({
                type: "conversation_initiation_client_data"
            }));
        });
        socket.addEventListener("message", function (event) {
            if (self.socket !== socket) {
                return;
            }
            self.handleMessage(event.data);
        });
        socket.addEventListener("close", function () {
            if (self.socket !== socket) {
                return;
            }
            self.socket = null;
            self.ready = false;
            self.rejectReadyWaiters(new Error("Shoutcaster disconnected"));
            self.rejectIntroduction(new Error("Shoutcaster disconnected during the introduction"));
            if (self.enabled) {
                self.status("Shoutcaster disconnected", "error");
            }
        });
        socket.addEventListener("error", function () {
            if (self.socket !== socket) {
                return;
            }
            self.rejectReadyWaiters(new Error("Shoutcaster connection failed"));
            self.status("Shoutcaster connection failed", "error");
        });
    };

    Commentator.prototype.send = function (type, payload) {
        if (!this.ready || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
            return false;
        }
        this.socket.send(JSON.stringify({
            type: type,
            text: typeof payload === "string" ? payload : JSON.stringify(payload)
        }));
        return true;
    };

    Commentator.prototype.handleMessage = function (raw) {
        var message;
        var metadata;
        try {
            message = JSON.parse(raw);
        } catch (_error) {
            return;
        }
        if (message.type === "conversation_initiation_metadata") {
            metadata = message.conversation_initiation_metadata_event || {};
            if (!/^pcm_\d+$/.test(String(metadata.agent_output_audio_format || "pcm_16000"))) {
                this.enabled = false;
                this.status("Set the ElevenAgent output format to PCM", "error");
                if (this.socket) {
                    this.socket.close();
                }
                return;
            }
            this.sampleRate = sampleRateFromFormat(metadata.agent_output_audio_format);
            this.ready = true;
            this.resolveReadyWaiters();
            this.status("Shoutcaster live", "ready");
            if (this.lastSnapshot) {
                this.send("contextual_update", publicSnapshot(this.lastSnapshot));
                this.lastContextAt = Date.now();
                if (
                    this.lastSnapshot.match.phase === "combat" &&
                    this.introducingRunId !== this.lastSnapshot.run_id
                ) {
                    this.pendingCue = {
                        event: broadcastJoinCue(this.lastSnapshot),
                        snapshot: this.lastSnapshot,
                        queuedAt: Date.now()
                    };
                    this.flushPendingCue();
                }
            }
            return;
        }
        if (message.type === "ping" && message.ping_event && this.socket) {
            this.socket.send(JSON.stringify({ type: "pong", event_id: message.ping_event.event_id }));
            return;
        }
        if (message.type === "agent_response") {
            this.speaking = true;
            if (typeof this.options.onCaption === "function") {
                this.options.onCaption(
                    compactText(message.agent_response_event && message.agent_response_event.agent_response, 280)
                );
            }
            return;
        }
        if (message.type === "audio" && message.audio_event && message.audio_event.audio_base_64) {
            this.speaking = true;
            this.queueAudio(message.audio_event.audio_base_64);
            return;
        }
        if (message.type === "agent_response_complete") {
            this.speaking = false;
            this.flushPendingCue();
        }
    };

    Commentator.prototype.queueAudio = function (base64) {
        var samples;
        var buffer;
        var source;
        var generation;
        if (!this.audioContext || !this.gainNode) {
            return;
        }
        samples = decodeBase64Pcm(base64);
        if (!samples.length) {
            return;
        }
        buffer = this.audioContext.createBuffer(1, samples.length, this.sampleRate);
        buffer.copyToChannel(samples, 0);
        source = this.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(this.gainNode);
        this.nextAudioTime = Math.max(this.audioContext.currentTime + 0.03, this.nextAudioTime);
        source.start(this.nextAudioTime);
        this.nextAudioTime += buffer.duration;
        this.audioGeneration += 1;
        generation = this.audioGeneration;
        source.onended = function () {
            // ElevenAgents does not emit agent_response_complete for every
            // configured client event set. Treat the final scheduled PCM
            // buffer as the authoritative end of a spoken response so queued
            // game cues cannot remain blocked forever.
            if (this.audioIdleTimer) {
                window.clearTimeout(this.audioIdleTimer);
            }
            this.audioIdleTimer = window.setTimeout(function () {
                if (
                    generation === this.audioGeneration &&
                    this.audioContext &&
                    this.audioContext.currentTime + 0.05 >= this.nextAudioTime
                ) {
                    this.audioIdleTimer = 0;
                    this.speaking = false;
                    this.resolveIntroduction();
                    this.flushPendingCue();
                }
            }.bind(this), 180);
        }.bind(this);
        if (typeof this.options.onAudio === "function") {
            this.options.onAudio({
                sample_rate: this.sampleRate,
                sample_count: samples.length,
                duration_seconds: buffer.duration,
                scheduled_at: this.nextAudioTime - buffer.duration
            });
        }
    };

    Commentator.prototype.commentaryPayload = function (event, snapshot) {
        var isIntroduction = event && event.type === "match_start";
        return {
            schema_version: 1,
            message_type: "commentary_cue",
            event_id: "round-" + snapshot.benchmark.current_round + "-" + snapshot.match.elapsed_seconds + "-" + event.type,
            round: snapshot.benchmark.current_round,
            elapsed_seconds: snapshot.match.elapsed_seconds,
            event: event,
            players: snapshot.players,
            delivery: {
                role: "funny American boxing-broadcast shoutcaster",
                maximum_words: isIntroduction ? 44 : 14,
                format: isIntroduction
                    ? "open with IN THE ROOTLY DOOM AGENT AREEENNAAAA, then use two theatrical ring-announcer sentences: introduce PLAYERRR ONE first and PLAYERRR TWO second, using each chosen name and one funny epithet"
                    : "one fast sentence combining the action and a short punchline",
                humor: "broad, reactive, varied, and understandable without Doom knowledge",
                avoid: ["technical jargon", "coordinates", "invented action", "repeated catchphrases"]
            }
        };
    };

    Commentator.prototype.rejectIntroduction = function (error) {
        var introduction = this.introduction;
        if (!introduction) {
            return;
        }
        this.introduction = null;
        window.clearTimeout(introduction.timer);
        introduction.reject(error);
    };

    Commentator.prototype.resolveIntroduction = function () {
        var introduction = this.introduction;
        if (!introduction) {
            return;
        }
        this.introduction = null;
        this.introducedRunId = introduction.runId;
        window.clearTimeout(introduction.timer);
        introduction.resolve();
    };

    Commentator.prototype.introduceMatch = function (input) {
        var self = this;
        var snapshot;
        var event;
        var trackedPromise;
        var runId = compactText(input && input.runId, 80);

        if (runId && this.introducedRunId === runId) {
            return Promise.resolve();
        }
        if (this.introductionPromise) {
            return this.introductionPromise;
        }
        this.expectIntroduction(runId);
        trackedPromise = this.waitUntilReady(15000).then(function () {
            snapshot = buildSnapshot({
                runId: runId,
                phase: "introducing",
                round: input.round,
                totalRounds: input.totalRounds,
                scenario: input.scenario,
                player1Name: input.player1Name,
                player2Name: input.player2Name,
                player1: { health: 150, alive: true },
                player2: { health: 150, alive: true }
            }, Date.now());
            event = matchIntroductionCue(snapshot);
            return new Promise(function (resolve, reject) {
                self.introduction = {
                    runId: runId,
                    resolve: resolve,
                    reject: reject,
                    timer: window.setTimeout(function () {
                        self.rejectIntroduction(new Error("Timed out waiting for the match introduction audio"));
                    }, 45000)
                };
                self.speaking = true;
                if (!self.send("user_message", self.commentaryPayload(event, snapshot))) {
                    self.speaking = false;
                    self.rejectIntroduction(new Error("Unable to send the match introduction"));
                    return;
                }
                self.lastCueAt = Date.now();
            });
        }).then(function (value) {
            if (self.introductionPromise === trackedPromise) {
                self.introductionPromise = null;
                self.introducingRunId = "";
            }
            return value;
        }, function (error) {
            if (self.introductionPromise === trackedPromise) {
                self.introductionPromise = null;
                self.introducingRunId = "";
            }
            throw error;
        });
        this.introductionPromise = trackedPromise;
        return trackedPromise;
    };

    Commentator.prototype.flushPendingCue = function () {
        var pending = this.pendingCue;
        var now = Date.now();
        var remainingDelay;

        if (this.pendingCueTimer) {
            window.clearTimeout(this.pendingCueTimer);
            this.pendingCueTimer = 0;
        }
        if (!pending || this.speaking) {
            return;
        }
        if (now - pending.queuedAt > cueMaxAgeMs(pending.event)) {
            this.pendingCue = null;
            return;
        }
        remainingDelay = cueDelayMs(pending.event, this.cooldownMs) - (now - this.lastCueAt);
        if (remainingDelay > 0) {
            this.pendingCueTimer = window.setTimeout(function () {
                this.pendingCueTimer = 0;
                this.flushPendingCue();
            }.bind(this), remainingDelay);
            return;
        }
        this.pendingCue = null;
        if (this.send("user_message", this.commentaryPayload(pending.event, pending.snapshot))) {
            this.lastCueAt = now;
        }
    };

    Commentator.prototype.update = function (input) {
        var now = Date.now();
        var snapshot = buildSnapshot(input, now);
        var event = chooseCue(this.lastSnapshot, snapshot);
        var shouldSendContext = !this.lastSnapshot ||
            this.lastSnapshot.run_id !== snapshot.run_id ||
            now - this.lastContextAt >= this.contextIntervalMs ||
            (event && event.type === "plan_change");

        this.lastSnapshot = snapshot;
        if (!this.enabled || !this.ready) {
            return snapshot;
        }
        if (
            event &&
            event.type === "match_start" &&
            (this.introducedRunId === snapshot.run_id || this.introducingRunId === snapshot.run_id)
        ) {
            event = null;
        }
        if (shouldSendContext && this.send("contextual_update", publicSnapshot(snapshot))) {
            this.lastContextAt = now;
        }
        if (event) {
            if (!this.pendingCue || cuePriority(event) >= cuePriority(this.pendingCue.event)) {
                this.pendingCue = { event: event, snapshot: snapshot, queuedAt: now };
            }
        }
        this.flushPendingCue();
        return snapshot;
    };

    return {
        Commentator: Commentator,
        buildSnapshot: buildSnapshot,
        chooseCue: chooseCue,
        latestPlan: latestPlan,
        publicSnapshot: publicSnapshot,
        cueDelayMs: cueDelayMs,
        cueMaxAgeMs: cueMaxAgeMs,
        sampleRateFromFormat: sampleRateFromFormat
    };
});
