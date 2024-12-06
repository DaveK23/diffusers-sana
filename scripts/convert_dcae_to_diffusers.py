import argparse
from typing import Any, Dict

import torch
from safetensors.torch import load_file

from diffusers import AutoencoderDC


def remove_keys_(key: str, state_dict: Dict[str, Any]):
    state_dict.pop(key)


def remap_qkv_(key: str, state_dict: Dict[str, Any]):
    # qkv = state_dict.pop(key)
    # q, k, v = torch.chunk(qkv, 3, dim=0)
    # parent_module, _, _ = key.rpartition(".qkv.conv.weight")
    # state_dict[f"{parent_module}.to_q.weight"] = q.squeeze()
    # state_dict[f"{parent_module}.to_k.weight"] = k.squeeze()
    # state_dict[f"{parent_module}.to_v.weight"] = v.squeeze()
    state_dict[key.replace("qkv.conv", "to_qkv")] = state_dict.pop(key)


VAE_KEYS_RENAME_DICT = {
    # common
    "main.": "",
    "op_list.": "",
    "context_module": "attn",
    "local_module": "conv_out",
    # NOTE: The below two lines work because scales in the available configs only have a tuple length of 1
    # If there were more scales, there would be more layers, so a loop would be better to handle this
    "aggreg.0.0": "to_qkv_multiscale.0.proj_in",
    "aggreg.0.1": "to_qkv_multiscale.0.proj_out",
    "norm.": "norm.norm.",
    "depth_conv.conv": "conv_depth",
    "inverted_conv.conv": "conv_inverted",
    "point_conv.conv": "conv_point",
    "point_conv.norm": "norm",
    "conv.conv.": "conv.",
    "conv1.conv": "conv1",
    "conv2.conv": "conv2",
    "conv2.norm": "norm",
    "proj.conv": "proj_out",
    "proj.norm": "norm_out",
    # encoder
    "encoder.project_in.conv": "encoder.conv_in",
    "encoder.project_out.0.conv": "encoder.conv_out",
    # decoder
    "decoder.project_in.conv": "decoder.conv_in",
    "decoder.project_out.0": "decoder.norm_out.norm",
    "decoder.project_out.2.conv": "decoder.conv_out",
}

VAE_SPECIAL_KEYS_REMAP = {
    "qkv.conv.weight": remap_qkv_,
}


def get_state_dict(saved_dict: Dict[str, Any]) -> Dict[str, Any]:
    state_dict = saved_dict
    if "model" in saved_dict.keys():
        state_dict = state_dict["model"]
    if "module" in saved_dict.keys():
        state_dict = state_dict["module"]
    if "state_dict" in saved_dict.keys():
        state_dict = state_dict["state_dict"]
    return state_dict


def update_state_dict_(state_dict: Dict[str, Any], old_key: str, new_key: str) -> Dict[str, Any]:
    state_dict[new_key] = state_dict.pop(old_key)


def convert_vae(ckpt_path: str, dtype: torch.dtype):
    original_state_dict = get_state_dict(load_file(ckpt_path))
    vae = AutoencoderDC(
        in_channels=3,
        latent_channels=32,
        encoder_block_types=(
            "ResBlock",
            "ResBlock",
            "ResBlock",
            "EfficientViTBlock",
            "EfficientViTBlock",
            "EfficientViTBlock",
        ),
        decoder_block_types=(
            "ResBlock",
            "ResBlock",
            "ResBlock",
            "EfficientViTBlock",
            "EfficientViTBlock",
            "EfficientViTBlock",
        ),
        block_out_channels=(128, 256, 512, 512, 1024, 1024),
        encoder_layers_per_block=(2, 2, 2, 3, 3, 3),
        decoder_layers_per_block=(3, 3, 3, 3, 3, 3),
        encoder_qkv_multiscales=((), (), (), (5,), (5,), (5,)),
        decoder_qkv_multiscales=((), (), (), (5,), (5,), (5,)),
        downsample_block_type="Conv",
        upsample_block_type="interpolate",
        decoder_norm_types="rms_norm",
        decoder_act_fns="silu",
        scaling_factor=0.41407,
    ).to(dtype=dtype)

    for key in list(original_state_dict.keys()):
        new_key = key[:]
        for replace_key, rename_key in VAE_KEYS_RENAME_DICT.items():
            new_key = new_key.replace(replace_key, rename_key)
        update_state_dict_(original_state_dict, key, new_key)

    for key in list(original_state_dict.keys()):
        for special_key, handler_fn_inplace in VAE_SPECIAL_KEYS_REMAP.items():
            if special_key not in key:
                continue
            handler_fn_inplace(key, original_state_dict)

    vae.load_state_dict(original_state_dict, strict=True)
    return vae


def get_vae_config(name: str):
    if name in ["dc-ae-f32c32-sana-1.0"]:
        config = {
            "latent_channels": 32,
            "encoder_block_types": ("ResBlock", "ResBlock", "ResBlock", "EViTS5_GLU", "EViTS5_GLU", "EViTS5_GLU"),
            "decoder_block_types": ("ResBlock", "ResBlock", "ResBlock", "EViTS5_GLU", "EViTS5_GLU", "EViTS5_GLU"),
            "block_out_channels": (128, 256, 512, 512, 1024, 1024),
            "encoder_qkv_multiscales": ((), (), (), (5,), (5,), (5,)),
            "decoder_qkv_multiscales": ((), (), (), (5,), (5,), (5,)),
            "encoder_layers_per_block": (2, 2, 2, 3, 3, 3),
            "decoder_layers_per_block": [3, 3, 3, 3, 3, 3],
            "downsample_block_type": "Conv",
            "upsample_block_type": "interpolate",
            "scaling_factor": 0.41407,
        }
    elif name in ["dc-ae-f32c32-in-1.0", "dc-ae-f32c32-mix-1.0"]:
        config = {
            "latent_channels": 32,
            "encoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "decoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "block_out_channels": [128, 256, 512, 512, 1024, 1024],
            "encoder_layers_per_block": [0, 4, 8, 2, 2, 2],
            "decoder_layers_per_block": [0, 5, 10, 2, 2, 2],
            "encoder_qkv_multiscales": ((), (), (), (), (), ()),
            "decoder_qkv_multiscales": ((), (), (), (), (), ()),
            "decoder_norm_types": ["batch_norm", "batch_norm", "batch_norm", "rms_norm", "rms_norm", "rms_norm"],
            "decoder_act_fns": ["relu", "relu", "relu", "silu", "silu", "silu"],
        }
    elif name in ["dc-ae-f128c512-in-1.0", "dc-ae-f128c512-mix-1.0"]:
        config = {
            "latent_channels": 512,
            "encoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "decoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "block_out_channels": [128, 256, 512, 512, 1024, 1024, 2048, 2048],
            "encoder_layers_per_block": [0, 4, 8, 2, 2, 2, 2, 2],
            "decoder_layers_per_block": [0, 5, 10, 2, 2, 2, 2, 2],
            "encoder_qkv_multiscales": ((), (), (), (), (), (), (), ()),
            "decoder_qkv_multiscales": ((), (), (), (), (), (), (), ()),
            "decoder_norm_types": [
                "batch_norm",
                "batch_norm",
                "batch_norm",
                "rms_norm",
                "rms_norm",
                "rms_norm",
                "rms_norm",
                "rms_norm",
            ],
            "decoder_act_fns": ["relu", "relu", "relu", "silu", "silu", "silu", "silu", "silu"],
        }
    elif name in ["dc-ae-f64c128-in-1.0", "dc-ae-f64c128-mix-1.0"]:
        config = {
            "latent_channels": 128,
            "encoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "decoder_block_types": [
                "ResBlock",
                "ResBlock",
                "ResBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
                "EfficientViTBlock",
            ],
            "block_out_channels": [128, 256, 512, 512, 1024, 1024, 2048],
            "encoder_layers_per_block": [0, 4, 8, 2, 2, 2, 2],
            "decoder_layers_per_block": [0, 5, 10, 2, 2, 2, 2],
            "encoder_qkv_multiscales": ((), (), (), (), (), (), ()),
            "decoder_qkv_multiscales": ((), (), (), (), (), (), ()),
            "decoder_norm_types": [
                "batch_norm",
                "batch_norm",
                "batch_norm",
                "rms_norm",
                "rms_norm",
                "rms_norm",
                "rms_norm",
            ],
            "decoder_act_fns": ["relu", "relu", "relu", "silu", "silu", "silu", "silu"],
        }

    return config


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vae_ckpt_path", type=str, default=None, help="Path to original vae checkpoint")
    parser.add_argument("--output_path", type=str, required=True, help="Path where converted model should be saved")
    parser.add_argument("--dtype", default="fp32", help="Torch dtype to save the model in.")
    return parser.parse_args()


DTYPE_MAPPING = {
    "fp32": torch.float32,
    "fp16": torch.float16,
    "bf16": torch.bfloat16,
}

VARIANT_MAPPING = {
    "fp32": None,
    "fp16": "fp16",
    "bf16": "bf16",
}


if __name__ == "__main__":
    args = get_args()

    dtype = DTYPE_MAPPING[args.dtype]
    variant = VARIANT_MAPPING[args.dtype]

    if args.vae_ckpt_path is not None:
        vae = convert_vae(args.vae_ckpt_path, dtype)
        vae.save_pretrained(args.output_path, safe_serialization=True, max_shard_size="5GB", variant=variant)
