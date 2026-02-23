package com.resona.client

data class PackInfo(
    val id: String,
    val name: String,
    val description: String
)

data class PackMetadata(
    val name: String,
    val description: String,
    val author: String,
    val version: String
)

data class OutfitInfo(
    val id: String,
    val name: String,
    val isDefault: Boolean
)

data class WebConfig(
    val sttMaxDuration: Double,
    val sttSilenceThreshold: Double,
    val sovitsEnabled: Boolean,
    val textReadSpeed: Double,
    val baseDisplayTime: Double,
    val activePack: String,
    val defaultOutfit: String,
    val characterName: String,
    val initialImageUrl: String?,
    val packMetadata: PackMetadata?,
    val availablePacks: List<PackInfo>
)

data class StatusMessage(
    val state: String,
    val text: String?,
    val imageUrl: String?
)

data class OutfitListMessage(
    val packId: String,
    val outfits: List<OutfitInfo>,
    val currentOutfit: String
)

data class OutfitChangedMessage(
    val outfitId: String,
    val imageUrl: String?
)

data class TimerEventMessage(
    val text: String,
    val audioUrl: String?,
    val imageUrl: String?,
    val duration: Double,
    val triggerAt: Double?
)
